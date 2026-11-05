"""Fresh/upgrade de un corte legacy real de esquema, sin adoptar por hostname."""
from datetime import datetime, timezone

from sqlalchemy import inspect, text

from tests.postgres.test_migracion_base_009 import migrate


async def seed_legacy(conn):
    await conn.execute(text("""INSERT INTO usuarios
      (id,username,nombre,password_hash,rol,activo,totp_habilitado,totp_secret,created_at)
      VALUES (71,'legacy-cierre','Legacy cierre','fixture-hash','ADMIN',true,true,'SECRETO-INVALIDO',:at)"""),
      {'at':datetime(2026,7,1,3)})
    await conn.execute(text("INSERT INTO catedras(id,nombre,titular_id,activa,created_at) VALUES (71,'Cátedra preservada',71,true,:at)"),{'at':datetime(2026,7,1,3)})
    await conn.execute(text("""INSERT INTO recurso_templates
      (id,nombre,tipo,modelo_servicio,default_vcpus,default_ram_mb,default_disk_gb,activo)
      VALUES (71,'Perfil legado','LXC','iaas',1,512,40,true)"""))
    for pid,state in [(71,'EN_DESPLIEGUE'),(72,'ERROR')]:
        await conn.execute(text("""INSERT INTO pedidos
          (id,catedra_id,solicitante_id,template_id,estado,tipo,modelo_servicio,vigencia_tipo,
           reserva_vcpus,reserva_ram_mb,reserva_disk_gb,created_at,updated_at)
          VALUES (:id,71,71,71,:state,'ALTA','iaas','personalizado',1,512,40,:at,:at)"""),
          {'id':pid,'state':state,'at':datetime(2026,7,1,3)})
        await conn.execute(text("""INSERT INTO servicios
          (id,catedra_id,pedido_id,template_id,proxmox_vmid,proxmox_node,tipo,estado,
           hostname,vcpus_asignados,ram_asignada_mb,disk_asignado_gb,exento_pausado,deployed_at)
          VALUES (:id,71,:id,71,:vmid,'pve1','lxc','ERROR','nombre-no-acredita-propiedad',1,512,40,false,:at)"""),
          {'id':pid,'vmid':'100' if pid==71 else '0100','at':datetime(2026,7,1,3)})
        await conn.execute(text("""INSERT INTO servicios_historial
          (servicio_id,estado_anterior,estado_nuevo,comentario,usuario_id,created_at)
          VALUES (:id,'running','error','Historia que no debe perderse',71,:at)"""),
          {'id':pid,'at':datetime(2026,7,1,3)})
    await conn.execute(text("""INSERT INTO metricas_snapshots
      (servicio_id,cpu_usage_percent,ram_usage_mb,disk_usage_gb,net_in_bytes,net_out_bytes,timestamp)
      VALUES (71,12,128,2,123,456,:at)"""),{'at':datetime(2026,7,1,3)})


async def test_upgrade_preserves_conflicts_unknown_dates_history_and_inconsistent_mfa(empty_pg_schema):
    async with empty_pg_schema.begin() as conn:
        await conn.run_sync(lambda c:migrate(c,'8b9c0d1e2f3a'))
        await seed_legacy(conn)
        await conn.run_sync(lambda c:migrate(c,'head'))
        assert await conn.scalar(text('SELECT count(*) FROM servicios'))==2
        assert await conn.scalar(text('SELECT count(*) FROM servicios_historial'))==2
        assert await conn.scalar(text('SELECT count(*) FROM pedidos'))==2
        assert set((await conn.execute(text('SELECT estado FROM pedidos'))).scalars())=={'EN_DESPLIEGUE','ERROR'}
        rows=(await conn.execute(text('SELECT proxmox_vmid,vence_at,identidad_infraestructura_id FROM servicios ORDER BY id'))).all()
        assert [r.proxmox_vmid for r in rows]==['100','0100']
        assert all(r.vence_at is None and r.identidad_infraestructura_id is None for r in rows)
        assert await conn.scalar(text('SELECT count(*) FROM vigencias_autorizadas'))==0
        assert await conn.scalar(text('SELECT count(*) FROM identidades_infraestructura'))==0
        user=(await conn.execute(text('SELECT totp_habilitado,habilitacion_inconsistente,totp_secret_encrypted FROM usuarios'))).one()
        assert user.totp_habilitado and user.habilitacion_inconsistente and user.totp_secret_encrypted is None
        assert await conn.scalar(text('SELECT timestamp FROM metricas_snapshots'))==datetime(2026,7,1,3,tzinfo=timezone.utc)
        columns=await conn.run_sync(lambda c:{x['name'] for x in inspect(c).get_columns('usuarios')})
        assert 'totp_secret' not in columns
        snapshots=(await conn.execute(text('SELECT asignacion_snapshot FROM pedidos ORDER BY id'))).scalars().all()
        assert all(s['vcpus']==1 and s['disk_gb']==40 and s['origen']=='legado_cantidades_autorizadas' for s in snapshots)
        assert await conn.scalar(text("SELECT count(*) FROM bitacora_cierre WHERE accion='retirar_campos_reserva'"))==2


async def test_fresh_schema_retires_plaintext_and_enforces_positive_resources(empty_pg_schema):
    import pytest
    from sqlalchemy.exc import IntegrityError
    async with empty_pg_schema.begin() as conn:
        await conn.run_sync(lambda c:migrate(c,'head'))
        users=await conn.run_sync(lambda c:{x['name'] for x in inspect(c).get_columns('usuarios')})
        services=await conn.run_sync(lambda c:{x['name'] for x in inspect(c).get_columns('servicios')})
        assert 'totp_secret' not in users and 'credenciales_acceso' not in services
        orders=await conn.run_sync(lambda c:{x['name'] for x in inspect(c).get_columns('pedidos')})
        assert not {'reserva_vcpus','reserva_ram_mb','reserva_disk_gb','reserva_expira_at'} & orders
        query=text("""INSERT INTO recurso_templates
          (nombre,tipo,modelo_servicio,default_vcpus,default_ram_mb,default_disk_gb,activo,revision)
          VALUES (:name,'LXC','iaas',:cpu,512,:disk,true,1)""")
        with pytest.raises(IntegrityError):
            async with conn.begin_nested():
                await conn.execute(query,{'name':'Inválido','cpu':-1,'disk':40})
        await conn.execute(query,{'name':'Disco grande válido','cpu':1,'disk':200})
        from app.database import Base
        for name in ['usuarios','pedidos','servicios','recurso_templates']:
            columns=await conn.run_sync(lambda c:{v['name'] for v in inspect(c).get_columns(name)})
            assert columns==set(Base.metadata.tables[name].columns.keys())


async def test_pending_secrets_block_retirement_and_reviewed_backfill_works_with_old_columns(empty_pg_schema):
    import pytest
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.models.bitacora_cierre import BitacoraCierre
    from app.services.backfill_cierre_service import planificar,aplicar
    from app.utils.secretos import configured_keyring
    from sqlalchemy import select
    async with empty_pg_schema.begin() as conn:
        await conn.run_sync(lambda c:migrate(c,'8b9c0d1e2f3a'))
        await seed_legacy(conn)
        await conn.run_sync(lambda c:migrate(c,'009_12_bitacora_cierre'))
        await conn.execute(text("UPDATE servicios SET credenciales_acceso=CAST(:value AS JSON) WHERE id=71"),
            {'value':'{"password":"only-test-legacy"}'})
        with pytest.raises(RuntimeError,match='cuarentena cifrada'):
            async with conn.begin_nested(): await conn.run_sync(lambda c:migrate(c,'head'))
        assert await conn.scalar(text("SELECT credenciales_acceso->>'password' FROM servicios WHERE id=71"))=='only-test-legacy'
        async with AsyncSession(bind=conn,expire_on_commit=False,join_transaction_mode='create_savepoint') as session:
            plan=await planificar(session)
            assert 'only-test-legacy' not in str(plan)
            await aplicar(session,plan,operador='operador-copia',referencia='copia-verificada-prueba')
            await session.commit()
            audit=await session.scalar(select(BitacoraCierre).where(BitacoraCierre.entidad_tipo=='servicio',BitacoraCierre.entidad_id=='71'))
            assert configured_keyring().decrypt(audit.legado_cifrado,context=f'cierre:{audit.id}:legado')['credenciales_acceso']['password']=='only-test-legacy'
        await conn.run_sync(lambda c:migrate(c,'head'))
        columns=await conn.run_sync(lambda c:{v['name'] for v in inspect(c).get_columns('servicios')})
        assert 'credenciales_acceso' not in columns
        assert await conn.scalar(text('SELECT count(*) FROM servicios'))==2
