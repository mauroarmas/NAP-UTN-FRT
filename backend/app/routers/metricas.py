from datetime import date, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, computed_field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.metrica import MetricaSnapshot
from app.models.servicio import Servicio
from app.models.usuario import RolUsuario
from app.routers.auth import get_current_user, require_admin
from app.services.acceso_service import catedras_visibles, es_visible
from app.services.metricas_service import capturar_snapshot_servicio, capturar_todos_los_servicios, obtener_historial, obtener_ultimo_snapshot
from app.services.resumen_metricas_service import consultar_consumo
from app.utils.clock import clock, db_utc
from app.utils.errors import error
from app.utils.soft_delete import excluir_dados_de_baja, vigente_o_404

router = APIRouter(prefix='/metricas', tags=['Métricas'])


class SnapshotResponse(BaseModel):
    id: int
    servicio_id: int
    cpu_usage_percent: float | None
    ram_usage_mb: float | None
    disk_usage_gb: float | None
    net_in_bytes: int | None
    net_out_bytes: int | None
    timestamp: datetime
    intervalo_at: datetime | None
    calidad: str
    estado_observado: str | None
    aplicacion_saludable: bool | None
    ram_max_mb: float | None
    disk_max_bytes: int | None
    vcpus_observadas: int | None
    uptime_s: int | None
    epoca_contador: str | None
    net_in_delta: int | None
    net_out_delta: int | None
    duracion_observada_s: int
    model_config = {'from_attributes': True}

    @field_validator('timestamp', 'intervalo_at')
    @classmethod
    def utc(cls, value):
        return db_utc(value) if value is not None else None

    @computed_field
    @property
    def net_in_bytes_exacto(self) -> str | None:
        return str(self.net_in_bytes) if self.net_in_bytes is not None else None

    @computed_field
    @property
    def net_out_bytes_exacto(self) -> str | None:
        return str(self.net_out_bytes) if self.net_out_bytes is not None else None

    @computed_field
    @property
    def net_in_delta_exacto(self) -> str | None:
        return str(self.net_in_delta) if self.net_in_delta is not None else None

    @computed_field
    @property
    def net_out_delta_exacto(self) -> str | None:
        return str(self.net_out_delta) if self.net_out_delta is not None else None


def periodo(desde, hasta):
    if any(v is not None and v.tzinfo is None for v in [desde,hasta]):
        raise error(422, 'periodo_invalido', 'Indicá fechas con zona horaria')
    if desde and hasta and hasta <= desde:
        raise error(422, 'periodo_invalido', 'El final debe ser posterior al inicio')


async def autorizado(db, service_id, actor):
    service = vigente_o_404(await db.get(Servicio, service_id), 'Servicio no encontrado')
    if not await es_visible(db, actor, service.catedra_id):
        raise error(403, 'sin_permisos', 'Sin permisos')
    return service


@router.post('/capturar')
async def capturar_metricas(current_user=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    from app.services import scheduler
    try:
        result = await scheduler.ejecutar('recolectar_metricas', db=db)
        return result['detalle']
    except scheduler.LockNoDisponible:
        raise error(409, 'trabajo_en_curso', 'La captura ya está en curso')


@router.post('/capturar/{servicio_id}', response_model=SnapshotResponse)
async def capturar_servicio(servicio_id: int, current_user=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    service = await autorizado(db, servicio_id, current_user)
    from app.services import scheduler
    try:
        async with scheduler.tomar_lock(db, 'recolectar_metricas'):
            sample = await capturar_snapshot_servicio(db, service)
    except scheduler.LockNoDisponible:
        raise error(409, 'trabajo_en_curso', 'La captura ya está en curso')
    if sample is None:
        raise error(409, 'observacion_no_disponible', 'El servicio no tiene una identidad LXC observable')
    return sample


@router.get('/resumen')
async def resumen_servicios(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    latest = select(MetricaSnapshot.id).where(MetricaSnapshot.servicio_id == Servicio.id)\
        .order_by(MetricaSnapshot.timestamp.desc(), MetricaSnapshot.id.desc()).limit(1).correlate(Servicio).scalar_subquery()
    query = excluir_dados_de_baja(select(Servicio, MetricaSnapshot).outerjoin(MetricaSnapshot, MetricaSnapshot.id == latest), Servicio)
    admin = current_user.rol == RolUsuario.ADMIN
    if not admin: query = query.where(Servicio.catedra_id.in_(await catedras_visibles(db, current_user)))
    result = []
    for service, sample in (await db.execute(query.order_by(Servicio.id))).all():
        observed = bool(sample and sample.calidad == 'confirmada')
        limits = {'cpu': sample.vcpus_observadas if observed else None,
            'ram': sample.ram_max_mb if observed else None, 'disco': sample.disk_max_bytes if observed else None}
        result.append({'servicio_id': service.id, 'catedra_id': service.catedra_id,
            'nombre': service.nombre_snapshot or f'Servicio #{service.id}', 'modelo_servicio': service.modelo_servicio,
            'vmid': service.proxmox_vmid if admin else None, 'node': service.proxmox_node if admin else None,
            'hostname': service.hostname, 'estado': service.estado.value,
            'estado_observado': sample.estado_observado if observed else None,
            'observado_at': db_utc(sample.timestamp).isoformat() if sample else None,
            'observacion_reciente': bool(observed and db_utc(sample.timestamp) >= clock.now()-timedelta(minutes=2)),
            'vcpus': limits['cpu'] if limits['cpu'] is not None else service.vcpus_asignados,
            'ram_max_mb': limits['ram'] if limits['ram'] is not None else service.ram_asignada_mb,
            'disk_max_gb': limits['disco']/1024**3 if limits['disco'] is not None else service.disk_asignado_gb,
            'limites_fuente': {k: 'observado' if v is not None else 'asignacion_estimada' for k,v in limits.items()},
            'ultimo_snapshot': SnapshotResponse.model_validate(sample).model_dump(mode='json') if sample else None})
    return result


@router.get('/consumo')
async def consumo(catedra_id: int, desde: date, hasta: date, limit: int = Query(default=500, ge=1, le=500),
    offset: int = Query(default=0, ge=0, le=1000000), current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not await es_visible(db, current_user, catedra_id): raise error(403, 'sin_permisos', 'Sin permisos')
    if hasta <= desde: raise error(422, 'periodo_invalido', 'El final debe ser posterior al inicio')
    return await consultar_consumo(db, catedra_id=catedra_id, desde=desde, hasta=hasta, limit=limit, offset=offset)


@router.get('/{servicio_id}/historial', response_model=list[SnapshotResponse])
async def historial_servicio(servicio_id: int, limit: int = Query(default=60, ge=1, le=500),
    desde: datetime | None = None, hasta: datetime | None = None,
    resolucion: Literal['minuto','hora','dia','auto'] = 'minuto',
    current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await autorizado(db, servicio_id, current_user)
    periodo(desde, hasta)
    return await obtener_historial(db, servicio_id, limit, desde=desde, hasta=hasta, resolucion=resolucion)


@router.get('/{servicio_id}/ultimo', response_model=SnapshotResponse)
async def ultimo_snapshot(servicio_id: int, current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await autorizado(db, servicio_id, current_user)
    sample = await obtener_ultimo_snapshot(db, servicio_id)
    if sample is None: raise error(404, 'sin_observaciones', 'Todavía no hay observaciones del servicio')
    return sample
