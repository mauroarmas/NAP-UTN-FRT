from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from app.database import Base


def migrate(connection, revision):
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / 'alembic.ini'))
    config.set_main_option('script_location', str(root / 'alembic'))
    config.attributes['connection'] = connection
    command.upgrade(config, revision)


async def test_fresh_install_has_shared_tables_and_partial_uniques(empty_pg_schema):
    async with empty_pg_schema.begin() as conn:
        await conn.run_sync(lambda sync: migrate(sync, 'head'))
        tables = await conn.run_sync(lambda sync: set(inspect(sync).get_table_names()))
        assert set(Base.metadata.tables) <= tables
        columns = await conn.run_sync(lambda sync: {col['name'] for col in inspect(sync).get_columns('recurso_templates')})
        assert 'definicion_version_id' in columns
        identity_columns = await conn.run_sync(lambda sync: {col['name'] for col in inspect(sync).get_columns('identidades_infraestructura')})
        assert {'definition_sha256', 'bundle_sha256'} <= identity_columns
        indices = (await conn.execute(text("SELECT indexdef FROM pg_indexes WHERE schemaname = current_schema()"))).scalars().all()
        assert any('uq_identidad_vmid_retenido' in value and 'WHERE' in value for value in indices)
        assert any('uq_operacion_abierta_identidad' in value and 'incierta' in value for value in indices)


async def test_upgrade_preserves_legacy_identity_without_inventing_snapshots(empty_pg_schema):
    async with empty_pg_schema.begin() as conn:
        await conn.run_sync(lambda sync: migrate(sync, '8b9c0d1e2f3a'))
        await conn.execute(text("INSERT INTO usuarios (id,username,email,nombre,password_hash,rol,activo,totp_habilitado,created_at) VALUES (42,'legacy009','legacy009@test.local','Legacy','test-only-hash','ADMIN',true,false,CURRENT_TIMESTAMP)"))
        await conn.execute(text("INSERT INTO catedras (id,nombre,activa,titular_id,created_at) VALUES (42,'Historia preservada',true,42,CURRENT_TIMESTAMP)"))
        await conn.run_sync(lambda sync: migrate(sync, 'head'))
        assert await conn.scalar(text('SELECT titular_id FROM catedras WHERE id = 42')) == 42
        assert await conn.scalar(text('SELECT username FROM usuarios WHERE id = 42')) == 'legacy009'
        assert await conn.scalar(text('SELECT count(*) FROM identidades_infraestructura')) == 0
        assert await conn.scalar(text('SELECT count(*) FROM evidencias')) == 0


async def test_upgrade_encrypts_confirmed_legacy_factor_and_preserves_inconsistent_mfa(empty_pg_schema):
    from app.utils.secretos import configured_keyring
    async with empty_pg_schema.begin() as conn:
        await conn.run_sync(lambda sync: migrate(sync, '009_01_consola'))
        await conn.execute(text("INSERT INTO usuarios (id,username,nombre,password_hash,rol,activo,totp_habilitado,totp_secret,created_at) VALUES (43,'legacy_mfa','Legacy MFA','test-only-hash','ADMIN',true,true,'JBSWY3DPEHPK3PXP',CURRENT_TIMESTAMP), (44,'inconsistent_mfa','Inconsistent','test-only-hash','CATEDRA_ADMIN',true,true,NULL,CURRENT_TIMESTAMP)"))
        await conn.run_sync(lambda sync: migrate(sync, 'head'))
        token = await conn.scalar(text('SELECT totp_secret_encrypted FROM usuarios WHERE id=43'))
        assert configured_keyring().decrypt(token, context='totp:43') == 'JBSWY3DPEHPK3PXP'
        columns=await conn.run_sync(lambda c:{col['name'] for col in inspect(c).get_columns('usuarios')})
        assert 'totp_secret' not in columns
        assert await conn.scalar(text('SELECT totp_habilitado FROM usuarios WHERE id=44')) is True
        assert await conn.scalar(text('SELECT habilitacion_inconsistente FROM usuarios WHERE id=44')) is True
