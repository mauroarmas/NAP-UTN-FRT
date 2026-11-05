"""Contadores legacy no adquieren precisión ni cobertura inventadas al migrar."""
from datetime import datetime, timezone

from sqlalchemy import inspect, text
from tests.postgres.test_migracion_base_009 import migrate


async def service_id(conn):
    # Esquema congelado en 009_10; no insertar con modelos de una versión futura.
    await conn.execute(text("""INSERT INTO usuarios(id,username,nombre,password_hash,rol,activo,
        totp_habilitado,created_at) VALUES (1,'observacion-migracion','Fixture','fixture','ADMIN',true,false,CURRENT_TIMESTAMP)"""))
    await conn.execute(text("INSERT INTO catedras(id,nombre,titular_id,activa,created_at) VALUES (1,'Fixture',1,true,CURRENT_TIMESTAMP)"))
    await conn.execute(text("""INSERT INTO recurso_templates(id,nombre,tipo,modelo_servicio,
        default_vcpus,default_ram_mb,default_disk_gb,activo,revision)
        VALUES (1,'Fixture','LXC','iaas',1,512,4,true,1)"""))
    return await conn.scalar(text("""INSERT INTO servicios(catedra_id,template_id,tipo,estado,
        vcpus_asignados,ram_asignada_mb,disk_asignado_gb,exento_pausado)
        VALUES (1,1,'lxc','RUNNING',1,512,4,false) RETURNING id"""))


async def test_upgrade_keeps_duplicates_and_original_float_values_without_claiming_coverage(empty_pg_schema):
    async with empty_pg_schema.begin() as conn:
        await conn.run_sync(lambda sync: migrate(sync, '009_10_identidad_preparacion'))
        sid = await service_id(conn)
        for offset, counter in [(10, 123.0), (20, float(2**54)), (30, -1.0), (40, 12.5)]:
            await conn.execute(text("""INSERT INTO metricas_snapshots
                (servicio_id,cpu_usage_percent,ram_usage_mb,disk_usage_gb,net_in_bytes,net_out_bytes,timestamp)
                VALUES (:sid,0,0,0,:counter,:counter,:at)"""),
                {'sid': sid, 'counter': counter, 'at': datetime(2026, 7, 1, 3, 0, offset)})
        await conn.run_sync(lambda sync: migrate(sync, 'head'))
        rows = (await conn.execute(text('SELECT * FROM metricas_snapshots ORDER BY id'))).mappings().all()
        assert len(rows) == 4
        assert [r['net_in_bytes'] for r in rows] == [123, None, None, None]
        assert [r['net_in_legacy'] for r in rows] == [123.0, float(2**54), -1.0, 12.5]
        assert all(r['calidad'] == 'no_confirmada' and r['intervalo_at'] is None for r in rows)
        assert all(r['net_in_delta'] is None and r['duracion_observada_s'] == 0 for r in rows)
        assert rows[0]['timestamp'] == datetime(2026, 7, 1, 3, 0, 10, tzinfo=timezone.utc)


async def test_schema_has_minute_unique_and_only_one_open_incident_per_kind(empty_pg_schema):
    async with empty_pg_schema.begin() as conn:
        await conn.run_sync(lambda sync: migrate(sync, 'head'))
        columns = await conn.run_sync(lambda sync: {c['name']: str(c['type']) for c in inspect(sync).get_columns('metricas_snapshots')})
        assert columns['net_in_bytes'] == 'BIGINT' and columns['net_out_bytes'] == 'BIGINT'
        assert 'aplicacion_saludable' in columns
        indexes = (await conn.execute(text('SELECT indexdef FROM pg_indexes WHERE schemaname=current_schema()'))).scalars().all()
        assert any('uq_metrica_servicio_minuto' in i and 'UNIQUE' in i for i in indexes)
        assert any('uq_incidente_abierto' in i and 'WHERE' in i and 'abierto' in i for i in indexes)
        tables = await conn.run_sync(lambda sync: set(inspect(sync).get_table_names()))
        assert {'incidentes', 'metricas_resumen_diario'} <= tables
