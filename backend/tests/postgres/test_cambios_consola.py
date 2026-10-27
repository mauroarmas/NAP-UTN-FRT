import asyncio

from fastapi import HTTPException
from sqlalchemy import select

from app.models.cambio_acceso_consola import CambioAccesoConsola
from app.models.usuario import Usuario
from app.models.usuario import RolUsuario
from tests import factories


async def test_two_transfers_of_same_native_identity_cannot_both_be_admitted(db, pg_sessions, admin, catedra, usuario_catedra):
    from app.services.consola_access_service import solicitar_cambio
    usuario_catedra.identidad_consola = 'docente@pve'
    usuario_catedra.inventario_consola = 'asignada'
    recipient = await factories.crear_usuario(db, 'recipient')
    await db.commit()
    actor_id, user_id, category_id, recipient_id = admin.id, usuario_catedra.id, catedra.id, recipient.id
    barrier = asyncio.Barrier(2)

    async def execute(key):
        async with pg_sessions() as session, session.begin():
            actor = await session.get(Usuario, actor_id)
            await barrier.wait()
            try:
                return await solicitar_cambio(session, usuario_objetivo_id=user_id, catedra_id=category_id,
                    accion='reasignar', cambios={'titular_id': recipient_id}, revision_esperada=1, actor=actor, clave=key)
            except HTTPException as exc:
                return exc.status_code

    results = await asyncio.gather(execute('first-transfer'), execute('second-transfer'))
    assert sum(item == 409 for item in results if isinstance(item, int)) == 1
    async with pg_sessions() as session:
        entries = (await session.scalars(select(CambioAccesoConsola))).all()
        assert len(entries) == 1


async def test_pending_degradations_never_block_all_administrators(db, pg_sessions, admin):
    from app.services.consola_access_service import solicitar_cambio
    other = await factories.crear_usuario(db, 'second-admin', rol=RolUsuario.ADMIN)
    for user in [admin, other]:
        user.identidad_consola = user.username + '@pve'
        user.inventario_consola = 'asignada'
    await db.commit()
    ids = [admin.id, other.id]
    barrier = asyncio.Barrier(2)

    async def degrade(identity):
        async with pg_sessions() as session, session.begin():
            actor = await session.get(Usuario, identity)
            await barrier.wait()
            try:
                return await solicitar_cambio(session, usuario_objetivo_id=identity, catedra_id=None,
                    accion='cambiar_rol', cambios={'rol': 'catedra_admin'}, revision_esperada=1,
                    actor=actor, clave=f'degrade-{identity}')
            except HTTPException as exc:
                return exc.status_code

    results = await asyncio.gather(*(degrade(identity) for identity in ids))
    assert sum(item == 409 for item in results if isinstance(item, int)) == 1
