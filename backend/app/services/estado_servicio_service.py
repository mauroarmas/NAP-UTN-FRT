"""Estado observado de servicios existentes, sin ejecutar órdenes en Proxmox."""
from sqlalchemy import select, or_

from app.models.servicio import Servicio, EstadoServicio
from app.models.identidad_infraestructura import IdentidadInfraestructura
from app.models.compromiso_capacidad import CompromisoCapacidad
from app.models.operacion_infraestructura import OperacionInfraestructura
from app.services import capacidad_service, identidad_infra_service, historial_service
from app.services.operacion_service import OPEN
from app.services.infraestructura_io import InfraNoVerificable
from app.utils.clock import clock


async def actualizar(db, servicio_id, *, pve=None):
    # El mismo lock que la admisión impide liberar capacidad mientras se admite
    # un arranque. Las operaciones abiertas conservan su propio reconciliador.
    async with capacidad_service.bloqueo_capacidad(db):
        service = await db.scalar(select(Servicio).where(Servicio.id == servicio_id)
            .with_for_update().execution_options(populate_existing=True))
        if not service or service.deleted_at or not service.identidad_infraestructura_id:
            raise InfraNoVerificable()
        identity = await db.get(IdentidadInfraestructura, service.identidad_infraestructura_id)
        if (not identity or identity.servicio_id != service.id or identity.ausencia_confirmada_at
            or str(identity.vmid) != service.proxmox_vmid or identity.nodo != service.proxmox_node):
            raise InfraNoVerificable()
        observation = await identidad_infra_service.observar(identity, pve=pve)
        if observation.estado != 'propia':
            raise InfraNoVerificable()
        active = await db.scalar(select(OperacionInfraestructura.id).where(
            or_(OperacionInfraestructura.servicio_id == service.id,
                OperacionInfraestructura.identidad_infraestructura_id == identity.id),
            OperacionInfraestructura.estado.in_(OPEN)).limit(1))
        if active:
            return observation
        ledger = await db.scalar(select(CompromisoCapacidad).where(
            CompromisoCapacidad.servicio_id == service.id,
            CompromisoCapacidad.liberado_at.is_(None)).with_for_update())
        if not ledger or ledger.identidad_infraestructura_id != identity.id or observation.config.get('lock'):
            raise InfraNoVerificable()
        before = service.estado
        stopped = observation.status == 'stopped'
        service.estado = (EstadoServicio.PAUSED if stopped and service.pausado_auto_at else
            EstadoServicio.STOPPED if stopped else EstadoServicio.RUNNING)
        service.observado_at = clock.now()
        from app.services.orquestacion_service import _matches
        matches = _matches(observation.config, service.asignacion_snapshot or {}, {'storage': ledger.storage_id})
        if matches:
            ledger.vcpus_retenidos = 0 if stopped else service.asignacion_snapshot['vcpus']
            ledger.ram_mb_retenida = 0 if stopped else service.asignacion_snapshot['ram_mb']
            ledger.estado, ledger.expira_at = 'materializado', None
            identity.estado, identity.ownership_verificada_at = 'materializada', clock.now()
        else:
            # Mostrar el estado no autoriza a ignorar cambios de recursos externos.
            ledger.estado, identity.estado = 'incierto', 'incierta'
        if before != service.estado:
            db.add(historial_service.registrar_servicio(service.id, before.value, service.estado.value,
                comentario='Estado observado en Proxmox; no se envió ninguna orden'))
        return observation


async def sincronizar(db):
    ids = list((await db.scalars(select(Servicio.id).where(Servicio.deleted_at.is_(None),
        Servicio.identidad_infraestructura_id.is_not(None)))).all())
    await db.commit()
    count = 0
    for service_id in ids:
        try:
            await actualizar(db, service_id)
            await db.commit()
            count += 1
        except InfraNoVerificable:
            await db.rollback()
    return {'afectados': count}
