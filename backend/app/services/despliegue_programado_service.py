"""Servicio de despacho de despliegues programados al inicio de vigencia (US3 - T072).
Despacha órdenes con intención aprobada para su fecha inicial, actor sistema,
clave estable por pedido/revisión y validación de vigencia/reserva/perfil.
"""
import hashlib
import logging
from sqlalchemy import select

from app.models.pedido import Pedido, EstadoPedido
from app.models.compromiso_capacidad import CompromisoCapacidad
from app.models.vigencia import VigenciaAutorizada
from app.services import capacidad_service, admision_service, scheduler
from app.utils.clock import clock, db_utc

logger = logging.getLogger(__name__)


async def procesar_agenda(db, *, pve=None) -> dict:
    """Procesa pedidos aprobados cuya fecha inicial programada ha sido alcanzada."""
    query = select(Pedido.id).where(
        Pedido.estado == EstadoPedido.APROBADO,
        Pedido.despliegue_programado_at.is_not(None),
        Pedido.despliegue_programado_at <= clock.now(),
        Pedido.deleted_at.is_(None),
    ).order_by(Pedido.id)
    candidate_ids = list((await db.scalars(query)).all())

    admitted = []
    omitted = []

    for pedido_id in candidate_ids:
        try:
            async with capacidad_service.bloqueo_capacidad(db):
                pedido = await db.scalar(
                    select(Pedido)
                    .where(Pedido.id == pedido_id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
                if not pedido or pedido.estado != EstadoPedido.APROBADO or pedido.deleted_at:
                    omitted.append({"id": pedido_id, "motivo": "estado_incompatible"})
                    continue

                if pedido.despliegue_programado_at is None or db_utc(pedido.despliegue_programado_at) > clock.now():
                    continue

                # Decisión posterior invalida la agenda anterior:
                if pedido.despliegue_revision_programada != pedido.revision_decision:
                    omitted.append({"id": pedido_id, "motivo": "revision_obsoleta"})
                    pedido.despliegue_programado_at = None
                    await db.commit()
                    continue

                # Validar que no haya una operación abierta
                previous = await admision_service._open_operation(db, pedido)
                if previous:
                    omitted.append({"id": pedido_id, "motivo": "operacion_en_curso"})
                    continue

                # Validar reserva de capacidad no caducada
                commitment = await admision_service._ledger(db, pedido_id)
                if not commitment or (commitment.expira_at and clock.now() >= db_utc(commitment.expira_at)):
                    omitted.append({"id": pedido_id, "motivo": "reserva_caducada"})
                    continue

                # Validar vigencia autorizada
                period = await db.scalar(
                    select(VigenciaAutorizada).where(
                        VigenciaAutorizada.pedido_id == pedido_id,
                        VigenciaAutorizada.revision_decision == pedido.revision_decision,
                        VigenciaAutorizada.revocada_at.is_(None),
                    )
                )
                if not period or clock.now() >= db_utc(period.fin_exclusivo_at):
                    omitted.append({"id": pedido_id, "motivo": "vigencia_vencida"})
                    continue

                # Validar perfil si corresponde
                if pedido.configuracion_despliegue_id:
                    from app.services.perfiles_service import validar_asignacion_aplicacion
                    try:
                        await validar_asignacion_aplicacion(db, pedido)
                    except Exception as exc:
                        omitted.append({"id": pedido_id, "motivo": "perfil_bloqueado"})
                        continue

                # Admitir despliegue con clave estable por pedido y revisión
                clave = f"agenda:despliegue:{pedido.id}:{pedido.revision_decision}"
                payload = {"origen": "despliegue_programado"}
                await admision_service._queue_deploy(
                    db, pedido, actor="despliegue_programado", clave=clave, payload=payload
                )
                pedido.despliegue_programado_at = None
                await db.commit()
                admitted.append(pedido.id)
        except Exception as exc:
            await db.rollback()
            logger.error(f"Error procesando agenda para pedido #{pedido_id}: {exc}")
            omitted.append({"id": pedido_id, "motivo": "error_despacho"})

    return {
        "afectados": len(admitted),
        "detalle": admitted,
        "omitidos": omitted,
    }


scheduler.registrar("procesar_agenda_despliegue", procesar_agenda, cada_minutos=1)
