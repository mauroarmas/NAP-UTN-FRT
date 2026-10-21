from types import SimpleNamespace

from sqlalchemy import select, func

from app.config import get_settings
from app.models.restauracion import Restauracion
from app.models.usuario import Usuario


async def test_cli_plan_is_read_only_and_apply_requires_explicit_copy_and_reference(
    admin, db, pg_sessions, monkeypatch, capsys,
):
    # db/pg_sessions pertenecen a su esquema propio; este test instala allí
    # sólo la marca Alembic para ejercer el CLI con create_all equivalente.
    from sqlalchemy import text
    from app.services.puesta_servicio_service import revision_esperada
    from scripts.preparar_restauracion import execute
    settings = get_settings()
    monkeypatch.setenv('NAP_SETTINGS_FILE', '/ruta-privada-cargada-por-fixture.json')
    monkeypatch.setattr(settings, 'restauracion_referencia', 'corte-cli')
    async with db.bind.begin() as conn:
        await conn.execute(text('CREATE TABLE alembic_version (version_num varchar(80) NOT NULL)'))
        await conn.execute(text('INSERT INTO alembic_version VALUES (:version)'), {'version':revision_esperada()})
    monkeypatch.setattr('app.database.engine', db.bind)
    monkeypatch.setattr('app.database.AsyncSessionLocal', pg_sessions)
    from os import environ
    monkeypatch.setattr(settings, 'database_url', environ['TEST_DATABASE_URL'])
    args = SimpleNamespace(base_copia='nap_test_009', referencia='corte-cli', operador=None, aplicar=False,
        evaluar=False, habilitar=False, reemitir_inicial=None, salida=None)
    user_id, version, password = admin.id, admin.auth_version, admin.password_hash
    assert await execute(args) == 0
    async with pg_sessions() as session:
        user = await session.get(Usuario, user_id)
        assert user.auth_version == version and user.password_hash == password
        assert await session.scalar(select(func.count()).select_from(Restauracion)) == 0
    args.aplicar, args.operador = True, 'operador-cli'
    assert await execute(args) == 0
    async with pg_sessions() as session:
        user = await session.get(Usuario, user_id)
        assert user.auth_version == version + 1 and user.password_hash == password
        assert await session.scalar(select(func.count()).select_from(Restauracion)) == 1
    output = capsys.readouterr().out
    assert password not in output and settings.database_url not in output
