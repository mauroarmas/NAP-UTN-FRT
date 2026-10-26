from sqlalchemy import text,inspect
from tests.postgres.test_migracion_base_009 import migrate
from tests.postgres.test_migracion_cierre_009 import seed_legacy
from app.database import Base


async def test_upgrade_009_preserva_historia_y_esquema_010(empty_pg_schema):
    async with empty_pg_schema.begin() as conn:
        await conn.run_sync(lambda c:migrate(c,'8b9c0d1e2f3a'))
        await seed_legacy(conn)
        await conn.run_sync(lambda c:migrate(c,'009_14_restauracion'))
        before=(await conn.execute(text('SELECT id,asignacion_snapshot FROM pedidos ORDER BY id'))).all()
        await conn.run_sync(lambda c:migrate(c,'head'))
        assert await conn.scalar(text('SELECT version_num FROM alembic_version'))=='011_01_despliegue_aplicaciones'
        after=(await conn.execute(text('SELECT id,asignacion_snapshot FROM pedidos ORDER BY id'))).all()
        assert before==after
        assert await conn.scalar(text('SELECT count(*) FROM pedidos WHERE seleccion_oferta_snapshot IS NOT NULL'))==0
        for table in ['incorporaciones_aplicacion','ensayos_preparacion','recursos_ensayo','operaciones_ensayo',
            'eventos_ensayo','artefactos_preparados','replicas_artefacto','presupuestos_builder','reservas_espacio_builder','publicaciones_oferta','accesos_aplicacion']:
            columns=await conn.run_sync(lambda c:{v['name'] for v in inspect(c).get_columns(table)})
            assert columns==set(Base.metadata.tables[table].columns.keys())
            assert await conn.scalar(text(f'SELECT count(*) FROM {table}'))==0
        assert await conn.scalar(text('SELECT count(*) FROM servicios_historial'))==2


async def test_migracion_quita_plazo_a_preparaciones_anteriores(empty_pg_schema):
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import select
    from app.models.usuario import Usuario
    from tests.test_ensayo_limpieza_010 import make_trial
    async with empty_pg_schema.begin() as conn:
        await conn.run_sync(lambda c:migrate(c,'8b9c0d1e2f3a'))
        await seed_legacy(conn)
        await conn.run_sync(lambda c:migrate(c,'010_03_seleccion_oferta'))
        async with AsyncSession(bind=conn,expire_on_commit=False) as session:
            actor=await session.scalar(select(Usuario).order_by(Usuario.id))
            trial=await make_trial(session,actor)
            await session.flush()
            identity=trial.id
            await session.commit()
        assert await conn.scalar(text('SELECT expires_at IS NOT NULL FROM ensayos_preparacion WHERE id=:id'),{'id':identity})
        await conn.run_sync(lambda c:migrate(c,'head'))
        assert await conn.scalar(text('SELECT expires_at IS NULL AND aviso_at IS NULL FROM ensayos_preparacion WHERE id=:id'),{'id':identity})
