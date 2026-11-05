"""Upgrade 010→011 conservador sobre esquemas PostgreSQL descartables."""
from pathlib import Path
from uuid import uuid4
import json

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError

from app.database import Base
from app.schemas.configuracion_despliegue import validar_documento, digest_configuracion
from tests.postgres.test_migracion_base_009 import migrate
from tests.postgres.test_migracion_cierre_009 import seed_legacy


NEW_TABLES = ['configuraciones_despliegue', 'secretos_despliegue', 'intentos_despliegue',
              'consolas_operacion', 'consola_fragmentos', 'reservas_red_aplicacion']
NEW_COLUMNS = {'recurso_templates': ['configuracion_despliegue_id'],
    'pedidos': ['configuracion_despliegue_id', 'despliegue_solicitado_at', 'despliegue_programado_at',
                'despliegue_revision_programada', 'despliegue_solicitado_por'],
    'servicios': ['configuracion_despliegue_id'], 'operaciones_infraestructura': ['operacion_raiz_id']}


def downgrade(connection):
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / 'alembic.ini'))
    config.set_main_option('script_location', str(root / 'alembic'))
    config.attributes['connection'] = connection
    command.downgrade(config, '010_06_acceso_aplicacion')


async def legacy(conn):
    await conn.run_sync(lambda c: migrate(c, '8b9c0d1e2f3a'))
    await seed_legacy(conn)
    await conn.run_sync(lambda c: migrate(c, '010_06_acceso_aplicacion'))
    identity = uuid4()
    await conn.execute(text("""INSERT INTO identidades_infraestructura
        (id,cluster_id,vmid,nodo,pool_catedra,resource_uuid,nonce_cifrado,definition_sha256,
         bundle_sha256,estado,claimed_at) VALUES (:id,'fixture-cluster',300,'pve1','legacy',
         :resource,'fixture-ciphertext',:sha,:sha,'materializada',CURRENT_TIMESTAMP)"""),
        {'id': identity, 'resource': uuid4(), 'sha': 'a'*64})
    await conn.execute(text("""INSERT INTO operaciones_infraestructura
        (id,tipo,actor_tipo,actor_id_normalizado,idempotency_key,request_hash,estado,fase,intento,
         creado_at,updated_at,next_poll_at,lease_generation) VALUES (:id,'desplegar','sistema',
         'fixture','legacy-terminal',:sha,'confirmada','finalizada',7,CURRENT_TIMESTAMP,
         CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,9)"""), {'id': uuid4(), 'sha': 'b'*64})


async def test_upgrade_preserves_every_legacy_value_and_adds_nullable_links(empty_pg_schema):
    async with empty_pg_schema.begin() as conn:
        await legacy(conn)
        tables = ['usuarios', 'catedras', 'recurso_templates', 'pedidos', 'servicios',
                  'identidades_infraestructura', 'operaciones_infraestructura']
        columns = {t: await conn.run_sync(lambda c, t=t: [v['name'] for v in inspect(c).get_columns(t)]) for t in tables}
        async def rows(t):
            names = ','.join('"' + c + '"' for c in columns[t])
            return (await conn.execute(text(f'SELECT {names} FROM {t} ORDER BY id'))).all()
        before = {t: await rows(t) for t in tables}
        await conn.run_sync(lambda c: migrate(c, '011_01_despliegue_aplicaciones'))
        assert await conn.scalar(text('SELECT version_num FROM alembic_version')) == '011_01_despliegue_aplicaciones'
        for table in tables: assert await rows(table) == before[table]
        for table, fields in NEW_COLUMNS.items():
            for field in fields:
                assert await conn.scalar(text(f'SELECT count(*) FROM {table} WHERE {field} IS NOT NULL')) == 0
        for table in NEW_TABLES:
            actual = await conn.run_sync(lambda c, table=table: {v['name'] for v in inspect(c).get_columns(table)})
            assert actual == set(Base.metadata.tables[table].columns.keys())
            assert await conn.scalar(text(f'SELECT count(*) FROM {table}')) == 0
            foreign_keys = await conn.run_sync(lambda c, table=table: inspect(c).get_foreign_keys(table))
            actual_fks = {(tuple(f['constrained_columns']), f['referred_table'], tuple(f['referred_columns'])) for f in foreign_keys}
            model_fks = {(tuple(c.parent.name for c in f.elements), f.elements[0].column.table.name,
                          tuple(c.column.name for c in f.elements)) for f in Base.metadata.tables[table].foreign_key_constraints}
            assert actual_fks == model_fks
        indices = (await conn.execute(text('SELECT indexdef FROM pg_indexes WHERE schemaname=current_schema()'))).scalars().all()
        for name in ['uq_red_direccion_activa', 'uq_red_slot_activo']:
            assert any(name in i and 'WHERE' in i for i in indices)
        await conn.run_sync(downgrade)
        for table in tables: assert await rows(table) == before[table]


async def insert_config(conn, document):
    document = validar_documento(document); identity = uuid4()
    await conn.execute(text("""INSERT INTO configuraciones_despliegue
        (id,codigo,revision,origen,modelo_servicio,documento,sha256,perfil_id,perfil_revision,
         perfil_sha256,estado,validaciones,creado_por,creado_at)
        VALUES (:id,'campus-demo',1,'imagen_docker','saas',CAST(:document AS JSON),:sha,
         'docker-ubuntu24',1,:profile,'validada',CAST(:validation AS JSON),71,CURRENT_TIMESTAMP)"""),
        {'id': identity, 'document': json.dumps(document), 'sha': digest_configuracion(document),
         'profile': document['perfil']['sha256'], 'validation': '{"instalacion":false}'})
    return identity


async def test_database_rejects_bulk_mutation_and_lossy_downgrade(empty_pg_schema, documento_docker):
    async with empty_pg_schema.begin() as conn:
        await legacy(conn)
        await conn.run_sync(lambda c: migrate(c, '011_01_despliegue_aplicaciones'))
        identity = await insert_config(conn, documento_docker)
        for sql in ["UPDATE configuraciones_despliegue SET revision=2 WHERE id=:id",
                    "UPDATE configuraciones_despliegue SET documento='{}'::json WHERE id=:id",
                    "DELETE FROM configuraciones_despliegue WHERE id=:id"]:
            with pytest.raises(DBAPIError):
                async with conn.begin_nested(): await conn.execute(text(sql), {'id': identity})
        with pytest.raises(RuntimeError, match='datos 011'):
            async with conn.begin_nested(): await conn.run_sync(downgrade)
        assert await conn.scalar(text('SELECT count(*) FROM configuraciones_despliegue')) == 1
        await conn.execute(text("UPDATE configuraciones_despliegue SET estado='retirada',retirada_at=CURRENT_TIMESTAMP WHERE id=:id"), {'id': identity})
        with pytest.raises(DBAPIError):
            async with conn.begin_nested():
                await conn.execute(text("UPDATE configuraciones_despliegue SET estado='validada',retirada_at=NULL WHERE id=:id"), {'id': identity})
        legacy_definition = uuid4()
        await conn.execute(text("""INSERT INTO definiciones_servicio
            (id,codigo,version,modelo_servicio,tipo_recurso,producto,manifest,estado,created_at,revision)
            VALUES (:id,'legacy-definition','1.0.0','iaas','lxc','linux','{}'::json,'borrador',CURRENT_TIMESTAMP,1)"""), {'id': legacy_definition})
        for table in ['recurso_templates', 'pedidos', 'servicios']:
            with pytest.raises(DBAPIError) as caught:
                async with conn.begin_nested():
                    await conn.execute(text(f'UPDATE {table} SET configuracion_despliegue_id=:id,definicion_version_id=:legacy WHERE id=71'),
                                       {'id': identity, 'legacy': legacy_definition})
            assert f'ck_{table}_origen_exclusivo' in str(caught.value)
