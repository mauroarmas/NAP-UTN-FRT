"""Planificador de los trabajos periódicos del portal.

Deliberadamente sin lógica de negocio: cada trabajo es una función de servicio
que recibe una sesión y devuelve un resumen. Esa función se prueba directamente,
se puede disparar a mano desde el endpoint de administración, y acá solo se la
llama con una cadencia. Si el planificador falla, la feature se degrada a
operación manual en lugar de romperse.

El lock en base existe porque el planificador vive dentro del proceso de la
aplicación: con varios workers, cada uno dispararía el mismo trabajo y los
vencimientos se aplicarían N veces.
"""

import logging
import os
import socket
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.job_lock import JobLock

logger = logging.getLogger(__name__)

# Un lock más viejo que esto se considera abandonado (proceso caído a mitad de
# camino) y se puede tomar de nuevo. Sin esto, un corte deja el trabajo colgado
# para siempre.
LOCK_MAX_EDAD = timedelta(minutes=30)


class LockNoDisponible(Exception):
    """El trabajo ya está corriendo en otro proceso."""


def _identidad() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


@asynccontextmanager
async def tomar_lock(db: AsyncSession, nombre: str):
    """Toma el lock del trabajo, o lanza ``LockNoDisponible``."""
    limite = datetime.utcnow() - LOCK_MAX_EDAD
    await db.execute(
        delete(JobLock).where(JobLock.nombre == nombre, JobLock.tomado_at < limite)
    )
    await db.commit()

    try:
        db.add(JobLock(nombre=nombre, tomado_por=_identidad()))
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise LockNoDisponible(nombre)

    try:
        yield
    finally:
        await db.execute(delete(JobLock).where(JobLock.nombre == nombre))
        await db.commit()


async def lock_tomado(db: AsyncSession, nombre: str) -> bool:
    result = await db.execute(select(JobLock).where(JobLock.nombre == nombre))
    return result.scalar_one_or_none() is not None


# --- Registro de trabajos ---------------------------------------------------

# nombre -> (función de servicio, minutos entre ejecuciones)
TRABAJOS: dict[str, tuple] = {}


def registrar(nombre: str, funcion, cada_minutos: int) -> None:
    """Da de alta un trabajo periódico. Lo llaman los módulos de servicio."""
    TRABAJOS[nombre] = (funcion, cada_minutos)


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

    if db is not None:
        async with tomar_lock(db, nombre):
            resultado = await funcion(db)
    else:
        async with AsyncSessionLocal() as propia:
            async with tomar_lock(propia, nombre):
                resultado = await funcion(propia)

    return {
        "job": nombre,
        "ejecutado_at": datetime.utcnow().isoformat(),
        **(resultado or {}),
    }


_scheduler: AsyncIOScheduler | None = None


def iniciar() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    _scheduler = AsyncIOScheduler()
    for nombre, (_, cada_minutos) in TRABAJOS.items():
        _scheduler.add_job(
            _ejecutar_silencioso,
            "interval",
            minutes=cada_minutos,
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
        logger.exception("Falló el trabajo periódico %s", nombre)


def detener() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
