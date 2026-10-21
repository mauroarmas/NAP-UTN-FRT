"""Cobertura autorizada por intervalos; una solicitud pendiente no la extiende."""
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pedido import EstadoPedido, Pedido, TipoPedido
from app.models.servicio import EstadoServicio, Servicio
from app.models.servicio_historial import ServicioHistorial
from app.services import historial_service, scheduler, vigencia_service
from app.utils.clock import clock
from app.utils.errors import error

AVISO_ANTICIPACION = timedelta(days=7)


def vencimiento_por_defecto(*args, **kwargs):
    raise error(422, 'vigencia_requerida', 'El servicio necesita un período autorizado explícito')


async def tiene_renovacion_pendiente(db: AsyncSession, servicio_id: int) -> bool:
    return await db.scalar(select(Pedido.id).where(Pedido.servicio_id == servicio_id,
        Pedido.tipo == TipoPedido.RENOVACION, Pedido.deleted_at.is_(None),
        Pedido.estado.in_([EstadoPedido.SOLICITADO, EstadoPedido.REQUIERE_AJUSTE, EstadoPedido.APROBADO, EstadoPedido.EN_DESPLIEGUE])).limit(1)) is not None


async def aplicar_vencimientos(db: AsyncSession) -> dict:
    from app.services.operacion_service import admitir_orden
    services = list((await db.scalars(select(Servicio).where(Servicio.deleted_at.is_(None)))).all())
    admitted, notices, omitted = [], [], []
    for service in services:
        periods = await vigencia_service.periodos_vigentes(db, service.id)
        coverage = vigencia_service.resumir_cobertura(periods, clock.now())
        if coverage['estado'] == 'sin_regularizar':
            omitted.append({'id': service.id, 'motivo': 'vigencia_sin_regularizar'})
            continue
        end = coverage['fin_actual']
        if end:
            # Para períodos menores de siete días el aviso corresponde desde
            # el primer ciclo. La clave histórica sigue el límite efectivo.
            if end - AVISO_ANTICIPACION <= clock.now():
                key = f'vigencia:aviso:{end.isoformat()}'
                previous = await db.scalar(select(ServicioHistorial.id).where(
                    ServicioHistorial.servicio_id == service.id, ServicioHistorial.evento_clave == key))
                if previous is None:
                    service.aviso_vencimiento_at = clock.now().replace(tzinfo=None)
                    db.add(historial_service.registrar_servicio(service.id, service.estado.value, service.estado.value,
                        comentario='Aviso de fin de cobertura: ' + end.isoformat(), evento_clave=key))
                    notices.append(service.id)
            continue
        if service.estado in {EstadoServicio.STOPPED, EstadoServicio.PAUSED}:
            continue
        boundary = coverage['fin_anterior'] or coverage['proximo_inicio']
        try:
            async with db.begin_nested():
                result = await admitir_orden(db, service.id, tipo='pausar', sistema='vencimiento',
                    clave=f'vencimiento:{service.id}:{boundary.isoformat()}',
                    motivo='Intervalo sin cobertura; detención pendiente de confirmación')
            if result.status_code == 202:
                admitted.append(service.id)
        except HTTPException as exc:
            omitted.append({'id': service.id, 'motivo': exc.detail.get('codigo', 'admision_no_confirmada') if isinstance(exc.detail, dict) else 'admision_no_confirmada'})
    await db.commit()
    return {'afectados': len(admitted), 'detalle': admitted, 'estado': 'operaciones_admitidas',
        'avisados': notices, 'omitidos': omitted}


scheduler.registrar('aplicar_vencimientos', aplicar_vencimientos, cada_minutos=1)
