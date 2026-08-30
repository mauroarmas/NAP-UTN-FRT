"""Ejecución manual de los trabajos periódicos y bitácora de la migración.

Los trabajos corren solos por planificador, pero poder dispararlos a mano es lo
que permite operarlos y depurarlos sin esperar la cadencia. Es la misma función
de servicio en ambos casos: no hay dos caminos de ejecución que puedan divergir.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.migracion import MigracionAccesoPerdido
from app.models.usuario import Usuario
from app.routers.auth import require_admin
from app.services import scheduler

router = APIRouter(prefix="/admin", tags=["Administración"])


@router.get("/jobs")
async def listar_jobs(current_user: Usuario = Depends(require_admin)):
    """Trabajos registrados y su cadencia."""
    return [
        {"nombre": nombre, "cada_minutos": cada}
        for nombre, (_, cada) in scheduler.TRABAJOS.items()
    ]


@router.post("/jobs/{nombre}")
async def ejecutar_job(
    nombre: str,
    current_user: Usuario = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Ejecuta un trabajo a demanda, bajo el mismo lock que usa el planificador."""
    try:
        return await scheduler.ejecutar(nombre, db=db)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe el trabajo '{nombre}'",
        )
    except scheduler.LockNoDisponible:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"El trabajo '{nombre}' ya está en ejecución",
        )


@router.get("/migracion/accesos-perdidos")
async def accesos_perdidos(
    current_user: Usuario = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Quiénes perdieron acceso al pasar a titular único.

    Una lista no vacía no es un error de la migración: es la consecuencia
    esperada de que una cátedra tenga un solo responsable. Lo que estaría mal es
    que la persona se enterara al no poder entrar.
    """
    result = await db.execute(
        select(MigracionAccesoPerdido).order_by(MigracionAccesoPerdido.username)
    )
    registros = result.scalars().all()
    return [
        {
            "usuario_id": r.usuario_id,
            "username": r.username,
            "catedra_id": r.catedra_id,
            "catedra_nombre": r.catedra_nombre,
            "migrado_at": r.migrado_at,
        }
        for r in registros
    ]
