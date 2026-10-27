import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.services import puesta_servicio_service
from tests.postgres.test_migracion_base_009 import migrate


async def test_boot_checks_schema_and_keys_read_only_without_migrating_or_calling_pve(empty_pg_schema,monkeypatch,proxmox):
    async with empty_pg_schema.begin() as conn:
        await conn.run_sync(lambda c:migrate(c,'head'))
    sessions=async_sessionmaker(empty_pg_schema,expire_on_commit=False)
    monkeypatch.setattr(puesta_servicio_service,'exigir_configuracion',lambda:None)
    async def validated_role(db): return None
    monkeypatch.setattr(puesta_servicio_service,'exigir_rol_runtime',validated_role)
    monkeypatch.setattr('app.database.AsyncSessionLocal',sessions)
    await puesta_servicio_service.comprobar_arranque('api')
    await puesta_servicio_service.comprobar_arranque('worker')
    async with empty_pg_schema.begin() as conn:
        await conn.execute(text("UPDATE alembic_version SET version_num='009_12_bitacora_cierre'"))
    for component in ['api','worker']:
        with pytest.raises(RuntimeError,match='migración release explícita'):
            await puesta_servicio_service.comprobar_arranque(component)
    async with empty_pg_schema.connect() as conn:
        assert await conn.scalar(text('SELECT version_num FROM alembic_version'))=='009_12_bitacora_cierre'
    assert not proxmox.creados and not proxmox.iniciados and not proxmox.eliminados


async def test_runtime_rejects_test_superuser_before_app_boot(db):
    with pytest.raises(RuntimeError,match='rol runtime'):
        await puesta_servicio_service.exigir_rol_runtime(db)


async def test_prepared_restore_blocks_both_production_boots_without_mutation(empty_pg_schema, monkeypatch):
    from app.services.restauracion_service import preparar_restauracion
    async with empty_pg_schema.begin() as conn:
        await conn.run_sync(lambda c: migrate(c, 'head'))
    sessions = async_sessionmaker(empty_pg_schema, expire_on_commit=False)
    async with sessions() as db:
        await preparar_restauracion(db, operador='operador', referencia='corte-arranque')
        await db.commit()
    monkeypatch.setattr(puesta_servicio_service, 'exigir_configuracion', lambda: None)
    async def validated_role(db): return None
    monkeypatch.setattr(puesta_servicio_service, 'exigir_rol_runtime', validated_role)
    monkeypatch.setattr('app.database.AsyncSessionLocal', sessions)
    for component in ['api', 'worker']:
        with pytest.raises(RuntimeError, match='Restauración pendiente'):
            await puesta_servicio_service.comprobar_arranque(component)
    async with empty_pg_schema.connect() as conn:
        assert await conn.scalar(text('SELECT count(*) FROM usuarios')) == 0
        assert await conn.scalar(text("SELECT estado FROM restauraciones")) == 'pendiente'
