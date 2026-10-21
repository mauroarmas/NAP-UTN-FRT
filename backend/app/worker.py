"""Ejecutor independiente. No iniciar desde el lifespan de la API."""
import asyncio
from contextlib import suppress
import logging
from uuid import uuid4

from app.database import AsyncSessionLocal
from app.services import operacion_service, scheduler

logger = logging.getLogger(__name__)


async def _heartbeat(sessions, lease):
    while True:
        await asyncio.sleep(10)
        try:
            async with sessions() as db:
                if not await operacion_service.heartbeat(db, lease):
                    return
                await db.commit()
        except Exception:
            logger.error('Heartbeat de operación no confirmado')
            return


async def procesar_una(sessions=AsyncSessionLocal, *, owner=None, pve=None, runner=None, after_dispatch=None):
    async with sessions() as db:
        from app.services.restauracion_service import exigir_habilitacion
        await exigir_habilitacion(db, componente='worker')
        lease = await operacion_service.reclamar(db, owner=owner or uuid4())
        await db.commit()
    if lease is None:
        return False
    task = asyncio.create_task(_heartbeat(sessions, lease))
    try:
        from app.services.orquestacion_service import procesar_lease
        await procesar_lease(sessions, lease, pve=pve, runner=runner, after_dispatch=after_dispatch)
    except Exception:
        logger.error('Operación pendiente de reconciliación por fallo del ejecutor')
        async with sessions() as db:
            await operacion_service.ceder(db, lease, incierta=True, segundos=30,
                error_codigo='ejecucion_no_confirmada', error_detalle_seguro='No se confirmó el resultado; la capacidad permanece comprometida')
            await db.commit()
    finally:
        # CancelledError/corte de proceso conservan el lease hasta takeover.
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
    return True


async def procesar_notificaciones(db):
    from app.services.notificacion_service import procesar_lote
    from sqlalchemy.ext.asyncio import async_sessionmaker
    sessions = async_sessionmaker(db.bind, expire_on_commit=False)
    await db.commit()
    await procesar_lote(sessions)
    return {'afectados': 0, 'detalle': 'Cola procesada con confirmación individual'}


async def limpiar_autenticacion(db):
    from sqlalchemy import update
    from app.models.autenticacion import SesionAutenticacion, DesafioAutenticacion
    from app.utils.clock import clock
    await db.execute(update(SesionAutenticacion).where(SesionAutenticacion.expira_at <= clock.now(),
        SesionAutenticacion.revoked_at.is_(None)).values(revoked_at=clock.now()))
    await db.execute(update(DesafioAutenticacion).where(DesafioAutenticacion.expira_at <= clock.now(),
        DesafioAutenticacion.consumido_at.is_(None), DesafioAutenticacion.revocado_at.is_(None))
        .values(revocado_at=clock.now(), secreto_pendiente_cifrado=None))
    await db.commit()
    return {'afectados': 0}


def registrar_trabajos():
    from app.services import capacidad_service, inactividad_service, vencimiento_service, alerta_service, resumen_metricas_service
    from app.services.reconciliacion_service import reconciliar_operaciones
    scheduler.registrar('recolectar_metricas', inactividad_service.recolectar_metricas, cada_minutos=1)
    scheduler.registrar('evaluar_inactividad', inactividad_service.evaluar_inactividad, cada_minutos=60)
    scheduler.registrar('aplicar_vencimientos', vencimiento_service.aplicar_vencimientos, cada_minutos=1)
    scheduler.registrar('expirar_reservas', capacidad_service.expirar_reservas, cada_minutos=1)
    scheduler.registrar('procesar_notificaciones', procesar_notificaciones, cada_minutos=1)
    scheduler.registrar('limpiar_autenticacion', limpiar_autenticacion, cada_minutos=1)
    scheduler.registrar('reconciliar_operaciones', reconciliar_operaciones, cada_minutos=1)
    scheduler.registrar('evaluar_alertas', alerta_service.evaluar_alertas, cada_minutos=1)
    scheduler.registrar('agregar_y_purgar_metricas', resumen_metricas_service.agregar_y_purgar, cada_minutos=1440, diario=True)
    scheduler.registrar('procesar_operaciones', procesar_operaciones, cada_segundos=5)


async def procesar_operaciones(db):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    sessions = async_sessionmaker(db.bind, expire_on_commit=False)
    parallel = 4 if db.bind.dialect.name == 'postgresql' else 1
    await db.commit()
    results = await asyncio.gather(*(procesar_una(sessions) for _ in range(parallel)))
    return {'afectados': sum(results)}


async def main():
    from app.config import get_settings
    if get_settings().app_env=='production':
        from app.services.puesta_servicio_service import comprobar_arranque
        await comprobar_arranque('worker')
    registrar_trabajos()
    scheduler.iniciar()
    try:
        # Los ticks manuales y automáticos comparten job/lock. Cada operación
        # conserva su propio lease y su siguiente poll, incluso tras reinicios.
        await asyncio.Event().wait()
    finally:
        scheduler.detener()


if __name__ == '__main__':
    asyncio.run(main())
