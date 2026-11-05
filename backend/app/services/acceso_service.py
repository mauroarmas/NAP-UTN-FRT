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
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catedra import Catedra
from app.models.usuario import Usuario, RolUsuario
from app.models.cambio_acceso_consola import CambioAccesoConsola
from app.models.servicio import Servicio
from app.models.pedido import Pedido
from app.utils.errors import error


async def usuario_actual(db, usuario):
    actual = await db.scalar(select(Usuario).where(Usuario.id == usuario.id)
                             .execution_options(populate_existing=True))
    if actual is None or not actual.activo:
        raise error(403, 'sin_permisos', 'La cuenta ya no tiene acceso operativo')
    pending = await db.scalar(select(CambioAccesoConsola.id).where(
        CambioAccesoConsola.usuario_id == actual.id,
        CambioAccesoConsola.estado.in_(['pendiente', 'revocacion_fallida']),
        or_(CambioAccesoConsola.accion.in_(['retirar', 'desactivar', 'cambiar_rol']),
            CambioAccesoConsola.catedra_id.is_(None)),
    ).limit(1))
    if pending:
        raise error(403, 'cambio_acceso_pendiente', 'La cuenta tiene un cambio de permisos pendiente')
    return actual


async def requiere_admin_actual(db, usuario):
    actual = await usuario_actual(db, usuario)
    if actual.rol != RolUsuario.ADMIN:
        raise error(403, 'sin_permisos', 'Se requieren permisos de administrador')
    return actual


async def catedras_visibles(db: AsyncSession, usuario: Usuario) -> set[int]:
    """Ids de las cátedras sobre las que la persona puede ver y operar.

    Para el rol administrador devuelve todas: su alcance es el sistema entero.
    """
    usuario = await usuario_actual(db, usuario)
    blocked = select(CambioAccesoConsola.catedra_id).where(
        CambioAccesoConsola.usuario_id == usuario.id,
        CambioAccesoConsola.catedra_id.is_not(None),
        CambioAccesoConsola.estado.in_(['pendiente', 'revocacion_fallida']),
    )
    if usuario.rol == RolUsuario.ADMIN:
        result = await db.execute(select(Catedra.id))
    else:
        result = await db.execute(
            select(Catedra.id).where(Catedra.titular_id == usuario.id)
        )
    return set(result.scalars().all()) - set((await db.scalars(blocked)).all())


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


async def requiere_acceso_servicio(db, usuario, servicio_id):
    servicio = await db.get(Servicio, servicio_id, populate_existing=True)
    if servicio is None or servicio.deleted_at is not None:
        raise error(404, 'servicio_no_encontrado', 'Servicio no encontrado')
    await requiere_acceso_catedra(db, usuario, servicio.catedra_id)
    return servicio


async def requiere_acceso_pedido(db, usuario, pedido_id):
    pedido = await db.get(Pedido, pedido_id, populate_existing=True)
    if pedido is None or pedido.deleted_at is not None:
        raise error(404, 'pedido_no_encontrado', 'Pedido no encontrado')
    await requiere_acceso_catedra(db, usuario, pedido.catedra_id)
    return pedido
