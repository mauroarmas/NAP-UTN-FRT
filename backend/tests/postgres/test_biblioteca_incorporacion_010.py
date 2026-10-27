import asyncio
from sqlalchemy import select, func
from app.models.usuario import Usuario
from tests import factories
from tests.fakes_biblioteca import FakeFuente, DRAWIO


async def test_importacion_concurrente_con_claves_distintas(pg_sessions, monkeypatch):
    from app.services import biblioteca_service
    from app.models.incorporacion_aplicacion import IncorporacionAplicacion
    from app.models.usuario import RolUsuario
    from app.schemas.biblioteca import IncorporacionCreate
    monkeypatch.setattr(biblioteca_service, 'get_fuente', lambda: FakeFuente())
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
            result = await biblioteca_service.incorporar(db, actor=actor, data=body, clave=key)
            await db.commit()
            return result
    a,b = await asyncio.gather(run('a'), run('b'))
    assert a.resultado['id'] == b.resultado['id']
    assert sorted([a.status_code, b.status_code]) == [200,201]
    async with pg_sessions() as db:
        assert await db.scalar(select(func.count()).select_from(IncorporacionAplicacion)) == 1
