"""Registro compartido; el planificador se inicia exclusivamente en el worker."""
import asyncio
from dataclasses import dataclass
import logging
import os
import socket
from uuid import UUID, uuid4
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database import AsyncSessionLocal
from app.models.job_lock import JobLock
from app.utils.clock import clock, db_utc

logger = logging.getLogger(__name__)
LOCK_MAX_EDAD = timedelta(minutes=30)  # Solo para interpretar un lock legado.
LEASE_SECONDS = 30


class LockNoDisponible(Exception):
    pass


@dataclass(frozen=True)
class LeaseJob:
    nombre: str
    owner: UUID
    generation: int


def _identidad():
    return f'{socket.gethostname()}:{os.getpid()}'[:100]


async def adquirir_job(db, nombre):
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    owner = uuid4()
    insert = pg_insert if db.bind.dialect.name == 'postgresql' else sqlite_insert
    now = clock.now()
    await db.execute(insert(JobLock).values(nombre=nombre, tomado_at=now.replace(tzinfo=None), tomado_por=_identidad(),
        owner_token=owner, generation=1, lease_until=now + timedelta(seconds=LEASE_SECONDS))
        .on_conflict_do_nothing(index_elements=['nombre']))
    row = await db.scalar(select(JobLock).where(JobLock.nombre == nombre).with_for_update().execution_options(populate_existing=True))
    if row.owner_token != owner:
        expiry = db_utc(row.lease_until) if row.lease_until else db_utc(row.tomado_at) + LOCK_MAX_EDAD
        if expiry > now:
            await db.rollback()
            raise LockNoDisponible(nombre)
        row.owner_token, row.generation = owner, row.generation + 1
        row.lease_until = now + timedelta(seconds=LEASE_SECONDS)
        row.tomado_at, row.tomado_por = now.replace(tzinfo=None), _identidad()
    await db.flush()
    lease = LeaseJob(nombre, owner, row.generation)
    await db.commit()
    return lease


def _job_owner(lease):
    return (JobLock.nombre == lease.nombre, JobLock.owner_token == lease.owner, JobLock.generation == lease.generation)


async def renovar_job(db, lease):
    result = await db.execute(update(JobLock).where(*_job_owner(lease), JobLock.lease_until > clock.now())
        .values(lease_until=clock.now() + timedelta(seconds=LEASE_SECONDS)).execution_options(synchronize_session=False))
    await db.commit()
    return result.rowcount == 1


async def liberar_job(db, lease):
    result = await db.execute(delete(JobLock).where(*_job_owner(lease)).execution_options(synchronize_session=False))
    await db.commit()
    return result.rowcount == 1


async def _renovacion(session_factory, lease, lost):
    while True:
        await asyncio.sleep(10)
        try:
            async with session_factory() as session:
                if not await renovar_job(session, lease):
                    lost.set()
                    return
        except Exception:
            lost.set()
            logger.error('Heartbeat de trabajo no confirmado')
            return


@asynccontextmanager
async def tomar_lock(db, nombre):
    lease = await adquirir_job(db, nombre)
    # Una sesión distinta para heartbeat; nunca comparte AsyncSession con el job.
    sessions = async_sessionmaker(db.bind, expire_on_commit=False)
    lost = asyncio.Event()
    task = asyncio.create_task(_renovacion(sessions, lease, lost))
    try:
        yield lease
        if lost.is_set():
            raise LockNoDisponible(nombre)
        current = await db.scalar(select(JobLock).where(*_job_owner(lease), JobLock.lease_until > clock.now()).with_for_update())
        if current is None:
            raise LockNoDisponible(nombre)
        await db.commit()
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        await db.rollback()
        await liberar_job(db, lease)


async def lock_tomado(db, nombre):
    row = await db.get(JobLock, nombre, populate_existing=True)
    if not row:
        return False
    expiry = db_utc(row.lease_until) if row.lease_until else db_utc(row.tomado_at) + LOCK_MAX_EDAD
    return expiry > clock.now()


# --- Registro de trabajos ---------------------------------------------------

# nombre -> (función de servicio, minutos entre ejecuciones)
TRABAJOS: dict[str, tuple] = {}
CADENCIAS_SEGUNDOS: dict[str, int] = {}
TRABAJOS_DIARIOS: set[str] = set()


def registrar(nombre: str, funcion, cada_minutos: int | None = None, *, cada_segundos: int | None = None, diario=False) -> None:
    """Da de alta un trabajo periódico. Lo llaman los módulos de servicio."""
    if (cada_minutos is None) == (cada_segundos is None):
        raise ValueError('Indicar una sola cadencia')
    cadence = cada_minutos if cada_minutos is not None else cada_segundos
    if type(cadence) is not int or cadence <= 0:
        raise ValueError('La cadencia debe ser positiva')
    if diario and cada_minutos != 1440:
        raise ValueError('El trabajo diario usa 1440 minutos')
    TRABAJOS[nombre] = (funcion, cada_minutos)
    if cada_segundos is not None: CADENCIAS_SEGUNDOS[nombre] = cada_segundos
    else: CADENCIAS_SEGUNDOS.pop(nombre, None)
    if diario: TRABAJOS_DIARIOS.add(nombre)
    else: TRABAJOS_DIARIOS.discard(nombre)


async def ejecutar(nombre: str, db: AsyncSession | None = None) -> dict:
    """Ejecuta un trabajo bajo lock. Es el único camino de ejecución.

    Lo usan tanto el planificador como el endpoint manual, para que no haya dos
    formas distintas de correr lo mismo.

    ``db`` se pasa cuando ya existe una sesión de la petición en curso; el
    planificador, que corre fuera de toda petición, abre la suya.
    """
    if nombre not in TRABAJOS:
        raise KeyError(nombre)
    funcion, _ = TRABAJOS[nombre]
    from app.services.restauracion_service import exigir_habilitacion

    if db is not None:
        await exigir_habilitacion(db, componente='worker')
        async with tomar_lock(db, nombre):
            resultado = await funcion(db)
    else:
        async with AsyncSessionLocal() as propia:
            await exigir_habilitacion(propia, componente='worker')
            async with tomar_lock(propia, nombre):
                resultado = await funcion(propia)

    return {
        "job": nombre,
        "ejecutado_at": clock.now().isoformat().replace("+00:00", "Z"),
        **(resultado or {}),
    }


_scheduler: AsyncIOScheduler | None = None


def iniciar() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    _scheduler = AsyncIOScheduler()
    for nombre, (_, cada_minutos) in TRABAJOS.items():
        if nombre in TRABAJOS_DIARIOS:
            from apscheduler.triggers.cron import CronTrigger
            from app.config import get_settings
            trigger = CronTrigger(hour=0, minute=5, timezone=get_settings().institutional_timezone)
            cadence = {}
        else:
            trigger = 'interval'
            cadence = ({'seconds': CADENCIAS_SEGUNDOS[nombre]} if nombre in CADENCIAS_SEGUNDOS else {'minutes': cada_minutos})
        _scheduler.add_job(
            _ejecutar_silencioso,
            trigger,
            **cadence,
            args=[nombre],
            id=nombre,
            # Si una corrida se atrasa, no acumular ejecuciones pendientes.
            coalesce=True,
            max_instances=1,
        )
    _scheduler.start()
    logger.info("Planificador iniciado con %d trabajos", len(TRABAJOS))
    return _scheduler


async def _ejecutar_silencioso(nombre: str) -> None:
    """Envoltorio para el planificador: un trabajo que falla no lo tumba."""
    try:
        await ejecutar(nombre)
    except LockNoDisponible:
        logger.debug("Trabajo %s ya en ejecución en otro proceso", nombre)
    except Exception:
        logger.error("Falló el trabajo periódico %s", nombre)


def detener() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
