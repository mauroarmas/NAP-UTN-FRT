"""Alcance de acceso por cátedra.

Fuente única de la pregunta "¿qué cátedras puede ver esta persona?".

Antes el aislamiento se resolvía comparando contra ``usuario.catedra_id`` en
cada router. Con una persona que puede tener varias cátedras, esa comparación
pasa a ser una pertenencia a un conjunto, y repetirla en seis lugares distintos
convierte cualquier olvido en una fuga de datos entre cátedras. Por eso vive
acá y no se replica: fuera de este módulo no debería quedar ninguna
comparación directa contra ids de cátedra.
"""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catedra import Catedra
from app.models.usuario import Usuario, RolUsuario


async def catedras_visibles(db: AsyncSession, usuario: Usuario) -> set[int]:
    """Ids de las cátedras sobre las que la persona puede ver y operar.

    Para el rol administrador devuelve todas: su alcance es el sistema entero.
    """
    if usuario.rol == RolUsuario.ADMIN:
        result = await db.execute(select(Catedra.id))
    else:
        result = await db.execute(
            select(Catedra.id).where(Catedra.titular_id == usuario.id)
        )
    return set(result.scalars().all())


async def requiere_acceso_catedra(
    db: AsyncSession, usuario: Usuario, catedra_id: int
) -> None:
    """Corta con 403 si la cátedra no está dentro del alcance de la persona."""
    if catedra_id not in await catedras_visibles(db, usuario):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tenés acceso a esta cátedra",
        )


async def es_visible(db: AsyncSession, usuario: Usuario, catedra_id: int) -> bool:
    """Versión no lanzante, para decidir sin abortar la petición."""
    return catedra_id in await catedras_visibles(db, usuario)
