"""Coordinar cambios de titular sin transferir acceso nativo anticipadamente."""

from uuid import uuid4
from sqlalchemy import select

from app.models.cambio_acceso_consola import CambioAccesoConsola
from app.models.usuario import Usuario
from app.services.consola_access_service import solicitar_cambio, OPEN
from app.utils.errors import error


async def preparar_cambio(db, category, changes, *, revision, actor, clave):
    pending = await db.scalar(select(CambioAccesoConsola.id).where(
        CambioAccesoConsola.catedra_id == category.id, CambioAccesoConsola.estado.in_(OPEN)).limit(1))
    critical = ('titular_id' in changes and changes['titular_id'] != category.titular_id) or (
        changes.get('activa') is False and category.activa)
    if pending and not (critical and clave):
        raise error(409, 'cambio_en_curso', 'La cátedra ya tiene un cambio de permisos pendiente', cambio_consola_id=str(pending))
    if not critical or category.titular_id is None:
        if revision is not None and revision != category.revision_admin:
            raise error(409, 'revision_desactualizada', 'Recargá los datos antes de guardar')
        return None
    previous = await db.get(Usuario, category.titular_id)
    if previous.inventario_consola == 'asignada' and (not clave or revision is None):
        raise error(422, 'revision_o_clave_ausente', 'El cambio nativo requiere revisión actual y clave idempotente')
    return await solicitar_cambio(db, usuario_objetivo_id=previous.id, catedra_id=category.id,
        accion='reasignar', cambios=changes, revision_esperada=revision or category.revision_admin,
        actor=actor, clave=clave or 'local:' + str(uuid4()))
