import asyncio

import pytest
from fastapi import HTTPException
from sqlalchemy import inspect, select, func, text

from app.database import Base
from app.models.restauracion import Restauracion, AccesoInicialRestaurado
from app.models.usuario import Usuario
from app.services.restauracion_service import preparar_restauracion
from tests.postgres.test_migracion_base_009 import migrate
from tests.postgres.test_migracion_cierre_009 import seed_legacy
from tests.test_restauracion_seguridad_009 import restored_rows


async def test_migration_adds_only_restore_control_and_does_not_seed_accounts(empty_pg_schema):
    async with empty_pg_schema.begin() as conn:
        await conn.run_sync(lambda c: migrate(c, 'head'))
        assert await conn.scalar(text('SELECT version_num FROM alembic_version')) == '011_01_despliegue_aplicaciones'
        for name in ['restauraciones', 'accesos_iniciales_restaurados']:
            columns = await conn.run_sync(lambda c: {v['name'] for v in inspect(c).get_columns(name)})
            assert columns == set(Base.metadata.tables[name].columns.keys())
            assert await conn.scalar(select(func.count()).select_from(Base.metadata.tables[name])) == 0
        assert await conn.scalar(text('SELECT count(*) FROM usuarios')) == 0


async def test_upgrade_allows_high_order_to_bind_created_service_and_requires_renewal_target(empty_pg_schema):
    from sqlalchemy.exc import IntegrityError
    async with empty_pg_schema.begin() as conn:
        await conn.run_sync(lambda c: migrate(c, '8b9c0d1e2f3a'))
        await seed_legacy(conn)
        await conn.run_sync(lambda c: migrate(c, '009_13_cierre_constraints'))
        await conn.execute(text('ALTER TABLE pedidos DROP CONSTRAINT ck_pedido_tipo_servicio'))
        await conn.execute(text("ALTER TABLE pedidos ADD CONSTRAINT ck_pedido_tipo_servicio CHECK "
                                "((tipo='ALTA' AND servicio_id IS NULL) OR (tipo='RENOVACION' AND servicio_id IS NOT NULL))"))
        await conn.run_sync(lambda c: migrate(c, 'head'))
        await conn.execute(text('UPDATE pedidos SET servicio_id=71 WHERE id=71'))
        assert await conn.scalar(text('SELECT servicio_id FROM pedidos WHERE id=71')) == 71
        with pytest.raises(IntegrityError):
            async with conn.begin_nested():
                await conn.execute(text("UPDATE pedidos SET tipo='RENOVACION', servicio_id=NULL WHERE id=71"))


@pytest.mark.parametrize('same_reference', [True, False])
async def test_concurrent_preparation_revokes_once_and_keeps_one_pending_cut(pg_sessions, db, admin, same_reference):
    await restored_rows(db, admin)
    user_id, version, encrypted = admin.id, admin.auth_version, admin.totp_secret_encrypted
    await db.rollback()
    async def run(reference):
        async with pg_sessions() as session:
            try:
                result = await preparar_restauracion(session, operador='operador', referencia=reference)
                await session.commit()
                return result['restauracion_id']
            except HTTPException as exc:
                await session.rollback()
                assert exc.status_code == 409
                return 'conflicto'
    results = await asyncio.gather(run('corte-uno'), run('corte-uno' if same_reference else 'corte-dos'))
    if same_reference: assert results[0] == results[1] and results[0] != 'conflicto'
    else: assert results.count('conflicto') == 1
    async with pg_sessions() as session:
        assert await session.scalar(select(func.count()).select_from(Restauracion)) == 1
        assert await session.scalar(select(func.count()).select_from(AccesoInicialRestaurado)) == 1
        user = await session.get(Usuario, user_id)
        assert user.auth_version == version + 1
        assert user.totp_habilitado and user.totp_secret_encrypted == encrypted


async def test_repara_constraint_antigua_en_instalacion_ya_migrada_a_01004(empty_pg_schema):
    from sqlalchemy.exc import IntegrityError
    async with empty_pg_schema.begin() as conn:
        await conn.run_sync(lambda c: migrate(c, '8b9c0d1e2f3a'))
        await seed_legacy(conn)
        await conn.run_sync(lambda c: migrate(c, '010_04_preparacion_simple'))
        await conn.execute(text('ALTER TABLE pedidos DROP CONSTRAINT ck_pedido_tipo_servicio'))
        await conn.execute(text("ALTER TABLE pedidos ADD CONSTRAINT ck_pedido_tipo_servicio CHECK "
                                "((tipo='ALTA' AND servicio_id IS NULL) OR (tipo='RENOVACION' AND servicio_id IS NOT NULL))"))
        before = await conn.scalar(text('SELECT count(*) FROM usuarios'))
        await conn.run_sync(lambda c: migrate(c, 'head'))
        await conn.execute(text('UPDATE pedidos SET servicio_id=71 WHERE id=71'))
        assert await conn.scalar(text('SELECT servicio_id FROM pedidos WHERE id=71')) == 71
        assert await conn.scalar(text('SELECT count(*) FROM usuarios')) == before
        with pytest.raises(IntegrityError):
            async with conn.begin_nested():
                await conn.execute(text("UPDATE pedidos SET tipo='RENOVACION', servicio_id=NULL WHERE id=71"))
