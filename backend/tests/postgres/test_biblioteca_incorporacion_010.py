import asyncio
from sqlalchemy import select, func
from app.models.usuario import Usuario
from tests import factories
from tests.fakes_biblioteca import DRAWIO
from fastapi import HTTPException


async def test_importaciones_retiradas_concurrentes_no_crean_registros(pg_sessions):
    from app.services import biblioteca_service
    from app.models.incorporacion_aplicacion import IncorporacionAplicacion
    from app.models.usuario import RolUsuario
    from app.schemas.biblioteca import IncorporacionCreate
    async with pg_sessions() as db:
        actor = await factories.crear_usuario(db, 'admin-biblioteca', rol=RolUsuario.ADMIN)
        actor_id = actor.id
        await db.commit()
    barrier = asyncio.Barrier(2)
    async def run(key):
        async with pg_sessions() as db:
            actor = await db.get(Usuario, actor_id)
            await barrier.wait()
            body = IncorporacionCreate(identidad_externa=DRAWIO['identidad_externa'], revision_fuente=DRAWIO['revision_fuente'])
            try:
                await biblioteca_service.incorporar(db, actor=actor, data=body, clave=key)
            except HTTPException as exc:
                assert exc.detail['codigo'] == 'origen_no_admitido'
                return exc.status_code
            raise AssertionError('Una ruta retirada no puede crear incorporaciones')
    a,b = await asyncio.gather(run('a'), run('b'))
    assert [a,b] == [422,422]
    async with pg_sessions() as db:
        assert await db.scalar(select(func.count()).select_from(IncorporacionAplicacion)) == 0
