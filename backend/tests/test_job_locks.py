"""Exclusión mutua de los trabajos periódicos.

El planificador vive dentro del proceso de la aplicación, así que con más de un
worker cada uno dispararía el mismo trabajo: los vencimientos se aplicarían N
veces y las reservas se liberarían N veces.

El lock en base es lo que lo impide. Es más simple que introducir una cola
externa y alcanza para un despliegue de instancia única, que es el caso real.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.job_lock import JobLock
from app.services import scheduler


async def test_el_lock_se_toma_y_se_libera(db):
    async with scheduler.tomar_lock(db, "prueba"):
        assert await scheduler.lock_tomado(db, "prueba") is True

    assert await scheduler.lock_tomado(db, "prueba") is False


async def test_un_segundo_proceso_no_puede_tomar_el_mismo_lock(db):
    """Es el escenario de dos workers disparando el mismo trabajo a la vez."""
    async with scheduler.tomar_lock(db, "concurrente"):
        with pytest.raises(scheduler.LockNoDisponible):
            async with scheduler.tomar_lock(db, "concurrente"):
                pass


async def test_trabajos_distintos_no_se_bloquean_entre_si(db):
    async with scheduler.tomar_lock(db, "uno"):
        async with scheduler.tomar_lock(db, "dos"):
            assert await scheduler.lock_tomado(db, "uno") is True
            assert await scheduler.lock_tomado(db, "dos") is True


async def test_el_lock_se_libera_aunque_el_trabajo_falle(db):
    """Un trabajo que revienta no puede dejar el lock tomado para siempre."""
    with pytest.raises(RuntimeError):
        async with scheduler.tomar_lock(db, "revienta"):
            raise RuntimeError("falla simulada")

    assert await scheduler.lock_tomado(db, "revienta") is False


async def test_un_lock_abandonado_se_recupera(db):
    """Si un proceso muere a mitad de camino, el lock no queda colgado eternamente."""
    db.add(
        JobLock(
            nombre="abandonado",
            tomado_at=datetime.utcnow() - scheduler.LOCK_MAX_EDAD - timedelta(minutes=1),
            tomado_por="proceso-muerto",
        )
    )
    await db.commit()

    async with scheduler.tomar_lock(db, "abandonado"):
        fila = (
            await db.execute(
                select(JobLock).where(JobLock.nombre == "abandonado")
            )
        ).scalar_one()
        assert fila.tomado_por != "proceso-muerto", "lo tomó el proceso vivo"


async def test_un_lock_reciente_no_se_pisa(db):
    """Solo se recupera lo abandonado, no lo que está corriendo ahora."""
    db.add(JobLock(nombre="en_curso", tomado_por="otro-worker"))
    await db.commit()

    with pytest.raises(scheduler.LockNoDisponible):
        async with scheduler.tomar_lock(db, "en_curso"):
            pass


async def test_los_cuatro_trabajos_estan_registrados():
    """Si alguno se cae del registro, deja de ejecutarse en silencio."""
    assert set(scheduler.TRABAJOS) == {
        "expirar_reservas",
        "aplicar_vencimientos",
        "evaluar_inactividad",
        "recolectar_metricas",
    }


async def test_ejecutar_un_trabajo_inexistente_falla_claro(db):
    with pytest.raises(KeyError):
        await scheduler.ejecutar("no_existe", db=db)
