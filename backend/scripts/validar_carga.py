"""Laboratorio SC-008: sólo PostgreSQL dedicado en loopback, nunca .env.

Ejecutar desde backend con su venv. `init` crea secretos privados; `prepare`
aplica Alembic y genera 100*129600 muestras; `serve` expone la API real en
loopback con PVE/runner simulados. Ningún comando elimina una base existente.
Los datos/evidencias sintéticos no acreditan aceptación institucional.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import stat
import sys
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
SERVICES = 100
SAMPLES_PER_SERVICE = 90 * 24 * 60
ORIGIN = 'http://localhost:4174'
API_PORT = 8044


def validate_url(value):
    from sqlalchemy.engine import make_url
    try:
        url = make_url(value)
        valid = (url.drivername == 'postgresql+asyncpg'
            and url.host in {'127.0.0.1', 'localhost', '::1'} and url.port == 55434
            and url.username == 'nap_perf' and url.database == 'nap_perf_009'
            and bool(url.password) and not url.query)
    except Exception:
        valid = False
    if not valid:
        raise ValueError('Se requiere la base dedicada nap_perf_009, rol nap_perf y loopback:55434')


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Clave duplicada en configuración')
        result[key] = value
    return result


def load_private(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 1024 * 1024):
            raise ValueError('La configuración debe ser regular, propia y privada (0600)')
        with os.fdopen(fd, 'r', closefd=False) as stream:
            return json.load(stream, object_pairs_hook=_unique)
    finally:
        os.close(fd)


def write_private(path, value):
    path = Path(path)
    if path.exists() or path.is_symlink():
        raise ValueError('El archivo privado ya existe; no se sobrescribe')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as output:
        json.dump(value, output, indent=2)
        output.write('\n')


def fixture_sql():
    return """INSERT INTO metricas_snapshots
      (servicio_id,timestamp,intervalo_at,calidad,estado_observado,aplicacion_saludable,
       cpu_usage_percent,ram_usage_mb,disk_usage_gb,net_in_bytes,net_out_bytes,
       uptime_s,epoca_contador,ram_max_mb,disk_max_bytes,vcpus_observadas,
       net_in_delta,net_out_delta,duracion_observada_s)
      SELECT :service_id, point, point, 'confirmada','running',true,
        20+(i%60),200+(i%100),1+(i%50)/100.0,
        1000000+i*1024::bigint,2000000+i*2048::bigint,
        1000+i*60::bigint,'fixture-009-epoch',512,4294967296::bigint,1,
        CASE WHEN i=0 THEN NULL ELSE 1024 END,
        CASE WHEN i=0 THEN NULL ELSE 2048 END,
        CASE WHEN i=0 THEN 0 ELSE 60 END
      FROM generate_series(0, :last_sample) AS g(i)
      CROSS JOIN LATERAL (SELECT CAST(:cutoff AS timestamptz)
        - (:last_sample-i)*interval '1 minute' AS point) AS p"""


def configure(config):
    validate_url(config['database_url'])
    if 'app.database' in sys.modules:
        raise ValueError('Iniciar un proceso nuevo: el motor de otra configuración ya fue importado')
    from app import config as module
    from app.config import Settings
    settings = Settings(_env_file=None, _env_prefix='NAP009_ISOLATED_',
        database_url=config['database_url'], app_debug=False, app_env='test',
        proxmox_host='perf.invalid', proxmox_token_value='', smtp_host='', smtp_user='', smtp_password='',
        app_frontend_url=ORIGIN, auth_allowed_origins=[ORIGIN],
        secret_key=config['jwt_key'], csrf_secret=config['csrf_key'],
        secret_keyring={'perf': config['encryption_key']}, secret_active_key='perf',
        infrastructure_profile={}, service_artifacts={}, network_profiles={}, runner_nodes={})
    module.get_settings = lambda: settings
    return settings


def init_private(path):
    from cryptography.fernet import Fernet
    parent = path.parent
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if parent.is_symlink() or stat.S_IMODE(parent.stat().st_mode) != 0o700:
        raise ValueError('Usar directorio privado 0700 sin enlaces')
    password = secrets.token_urlsafe(32)
    config = {'run_id': str(uuid4()),
        'database_url': f'postgresql+asyncpg://nap_perf:{password}@127.0.0.1:55434/nap_perf_009',
        'jwt_key': secrets.token_urlsafe(48), 'csrf_key': secrets.token_urlsafe(48),
        'encryption_key': Fernet.generate_key().decode(),
        'users': [{'username': f'perf-{role}-{i}', 'role': role, 'password': secrets.token_urlsafe(24)}
            for role in ('admin', 'catedra_admin') for i in range(5)]}
    write_private(path, config)
    write_private(parent / 'pg-password.json', {'password': password})
    # Docker usa este archivo, no variables/argumentos con la contraseña.
    fd = os.open(parent / 'pg-password', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as output:
        output.write(password + '\n')
    print('Configuración privada creada; falta iniciar PostgreSQL dedicado y ejecutar prepare')


async def _seed_entities(config, cutoff):
    from app.database import AsyncSessionLocal
    from app.models.usuario import Usuario, RolUsuario
    from app.models.catedra import Catedra
    from app.models.pedido import Pedido, EstadoPedido, ModeloServicio
    from app.models.recurso_template import RecursoTemplate
    from app.models.servicio import Servicio, EstadoServicio
    from app.models.servicio_historial import ServicioHistorial
    from app.models.identidad_infraestructura import IdentidadInfraestructura
    from app.models.compromiso_capacidad import CompromisoCapacidad
    from app.models.vigencia import VigenciaAutorizada
    from app.utils.security import get_password_hash
    from app.utils.secretos import configured_keyring
    cluster, fixture = str(uuid4()), {'services': [], 'users': [], 'cluster_uuid': None}
    fixture['cluster_uuid'] = cluster
    async with AsyncSessionLocal() as db:
        users = []
        for item in config['users']:
            user = Usuario(username=item['username'], email=item['username']+'@example.org',
                nombre=item['username'], password_hash=get_password_hash(item['password']),
                rol=RolUsuario(item['role']), activo=True, debe_cambiar_password=False,
                recibir_notificaciones_email=False, inventario_consola='sin_identidad',
                inventario_consola_actor='fixture-009', inventario_consola_ref='SIMULADO-SC008')
            db.add(user); await db.flush(); users.append(user)
            fixture['users'].append({'id':user.id,'username':user.username,'role':item['role']})
        teachers = users[5:]
        categories = []
        for i in range(10):
            category = Catedra(nombre=f'Rendimiento {i:02}', titular_id=teachers[i//2].id)
            db.add(category); await db.flush(); categories.append(category)
        templates = []
        for model in ModeloServicio:
            template = RecursoTemplate(nombre=f'Histórico simulado {model.value}', modelo_servicio=model,
                activo=False, default_vcpus=1, default_ram_mb=512, default_disk_gb=4)
            db.add(template); await db.flush(); templates.append(template)
        for i in range(SERVICES):
            category, template = categories[i//10], templates[i%3]
            snapshot = {'template_id':template.id,'vcpus':1,'ram_mb':512,'disk_gb':4,
                'tipo':'lxc','modelo_servicio':template.modelo_servicio.value, 'nombre':template.nombre}
            pedido = Pedido(catedra_id=category.id, solicitante_id=category.titular_id,
                template_id=template.id, modelo_servicio=template.modelo_servicio,
                descripcion_requerimientos=f'SC008-{i:03} datos sintéticos de rendimiento',
                estado=EstadoPedido.ACTIVO if i%2==0 else EstadoPedido.SUSPENDIDO,
                created_at=(cutoff-timedelta(days=i%90)).replace(tzinfo=None),
                asignacion_snapshot=snapshot, revision_decision=1)
            db.add(pedido); await db.flush()
            identity_uuid, nonce = uuid4(), secrets.token_urlsafe(24)
            identity = IdentidadInfraestructura(cluster_id=cluster, vmid=1000+i,nodo='pve1',
                pool_catedra=f'catedra-{category.id}', resource_uuid=identity_uuid,
                nonce_cifrado=configured_keyring().encrypt(nonce,context=f'infra:{identity_uuid}:nonce'),
                estado='materializada',ownership_verificada_at=cutoff)
            db.add(identity); await db.flush()
            service = Servicio(catedra_id=category.id, pedido_id=pedido.id, template_id=template.id,
                proxmox_vmid=str(1000+i),proxmox_node='pve1', hostname=f'sc008-{i:03}',
                estado=EstadoServicio.RUNNING,modelo_servicio=template.modelo_servicio.value,
                nombre_snapshot=template.nombre,asignacion_snapshot=snapshot,
                vcpus_asignados=1,ram_asignada_mb=512,disk_asignado_gb=4,
                identidad_infraestructura_id=identity.id,disponibilidad_aplicacion='no_verificada',
                deployed_at=(cutoff-timedelta(days=90)).replace(tzinfo=None))
            db.add(service); await db.flush(); identity.servicio_id=service.id
            db.add(CompromisoCapacidad(pedido_id=pedido.id,servicio_id=service.id,
                identidad_infraestructura_id=identity.id,nodo='pve1',storage_id='local-lvm',
                storage_scope='node:pve1:local-lvm',vcpus_retenidos=1,ram_mb_retenida=512,
                disk_bytes_retenidos=4*1024**3,estado='materializado'))
            db.add(ServicioHistorial(servicio_id=service.id,estado_anterior='stopped',estado_nuevo='running',
                created_at=(cutoff-timedelta(days=90)).replace(tzinfo=None),evento_clave='fixture-009',
                actor_tipo='sistema',decision_metadata={'asignacion':snapshot,'catedra_id':category.id}))
            start,end=cutoff-timedelta(days=91),cutoff+timedelta(days=30)
            db.add(VigenciaAutorizada(pedido_id=pedido.id,revision_decision=1,servicio_id=service.id,
                modalidad='personalizado',desde_local=start.date(),hasta_local=end.date(),
                zona_horaria='America/Argentina/Tucuman',inicio_at=start,fin_exclusivo_at=end,
                aprobado_at=start,aprobado_por=users[0].id))
            fixture['services'].append({'id':service.id,'pedido_id':pedido.id,'category_id':category.id,
                'teacher_id':category.titular_id,'model':template.modelo_servicio.value,
                'hostname':service.hostname,'pedido_estado':pedido.estado.value})
        from sqlalchemy import text
        await db.execute(text('UPDATE nap009_fixture_meta SET fixture=CAST(:fixture AS jsonb) WHERE run_id=:run'),
            {'fixture':json.dumps(fixture),'run':config['run_id']})
        await db.commit()
    return fixture


async def prepare(config, directory):
    from sqlalchemy import text
    from app.database import engine
    started = datetime.now(timezone.utc)
    async with engine.connect() as control:
        await control.execute(text('SELECT pg_advisory_lock(9009117)'))
        tables = (await control.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'"))).scalars().all()
        if tables and 'nap009_fixture_meta' not in tables:
            raise ValueError('Base no marcada: se rechaza modificar datos existentes')
        if not tables:
            await control.execute(text('CREATE TABLE nap009_fixture_meta (run_id text PRIMARY KEY,cutoff timestamptz NOT NULL,fixture jsonb)'))
            await control.execute(text('INSERT INTO nap009_fixture_meta(run_id,cutoff) VALUES (:run,:cutoff)'),
                {'run':config['run_id'],'cutoff':started.replace(second=0,microsecond=0)})
            await control.commit()
        row = (await control.execute(text('SELECT run_id,cutoff,fixture FROM nap009_fixture_meta'))).one()
        if row.run_id != config['run_id']:
            raise ValueError('La base pertenece a otro ensayo; no se sobrescribe')
        cutoff, fixture = row.cutoff, row.fixture
        await control.commit()
        def upgrade(connection):
            from alembic.config import Config
            from alembic import command
            alembic = Config(str(ROOT/'backend/alembic.ini'))
            alembic.set_main_option('script_location',str(ROOT/'backend/alembic'))
            alembic.attributes['connection']=connection
            command.upgrade(alembic,'head')
        async with engine.begin() as connection:
            await connection.run_sync(upgrade)
        if fixture is None:
            fixture = await _seed_entities(config,cutoff)
        for service in fixture['services']:
            async with engine.begin() as conn:
                count = await conn.scalar(text('SELECT count(*) FROM metricas_snapshots WHERE servicio_id=:id'),{'id':service['id']})
                if count == SAMPLES_PER_SERVICE:
                    continue
                if count:
                    raise ValueError('Detalle parcial ajeno a una transacción del generador; revisar sin borrar')
                await conn.execute(text(fixture_sql()),{'service_id':service['id'],
                    'cutoff':cutoff,'last_sample':SAMPLES_PER_SERVICE-1})
            if service['id']%10==0:
                print(f"Detalle generado: {service['id']}/{SERVICES}",flush=True)
        async with engine.begin() as conn:
            await conn.execute(text('ANALYZE metricas_snapshots'))
        diagnostic = await diagnostics(engine, fixture)
        fixture.update(cutoff=cutoff.isoformat(),samples=SERVICES*SAMPLES_PER_SERVICE,
            started_at=started.isoformat(),finished_at=datetime.now(timezone.utc).isoformat(),
            environment='simulado',origin=ORIGIN,api_port=API_PORT,diagnostic=diagnostic,
            source=source_provenance())
        target=directory/'fixture.json'
        if target.exists():
            previous=load_private(target)
            if previous['cluster_uuid'] != fixture['cluster_uuid']:
                raise ValueError('Recibo ajeno al ensayo')
            # Reemplazo atómico en el directorio privado, sin seguir enlaces.
            temporary=directory/('fixture-'+uuid4().hex+'.json'); write_private(temporary,fixture)
            os.replace(temporary,target)
        else:
            write_private(target,fixture)
        await control.execute(text('SELECT pg_advisory_unlock(9009117)'))
    await engine.dispose()
    print(f'Fixture preparado: {SERVICES} servicios, {SERVICES*SAMPLES_PER_SERVICE} muestras; sin aceptación SC-008')


def source_provenance():
    import subprocess
    files=[]
    for folder in ('backend/app','backend/alembic','frontend/src'):
        files.extend(p for p in (ROOT/folder).rglob('*') if p.is_file() and p.suffix in {'.py','.jsx','.js','.css'})
    files += [ROOT/p for p in ('backend/requirements.lock','frontend/package-lock.json')]
    hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}
    return {'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'working_tree':'cambios sin commit; hashes por archivo','sha256':hashes}


async def diagnostics(engine,fixture):
    from sqlalchemy import text
    async with engine.connect() as conn:
        version=await conn.scalar(text('SHOW server_version'))
        size=await conn.scalar(text('SELECT pg_database_size(current_database())'))
        indexes=(await conn.execute(text("SELECT indexname,indexdef FROM pg_indexes WHERE tablename='metricas_snapshots'"))).mappings().all()
        plan=await conn.scalar(text('EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) SELECT * FROM metricas_snapshots WHERE servicio_id=:id ORDER BY timestamp DESC LIMIT 1'),{'id':fixture['services'][0]['id']})
        counts=(await conn.execute(text('SELECT servicio_id,count(*) n,min(timestamp) desde,max(timestamp) hasta FROM metricas_snapshots GROUP BY servicio_id ORDER BY servicio_id'))).mappings().all()
        if len(counts)!=SERVICES or any(r['n']!=SAMPLES_PER_SERVICE for r in counts):
            raise ValueError('El volumen del fixture no coincide con 100*129600')
        settings={key:await conn.scalar(text('SHOW '+key)) for key in ('shared_buffers','work_mem','maintenance_work_mem','max_connections','fsync','synchronous_commit')}
    return {'postgresql':version,'database_bytes':size,'indexes':[dict(x) for x in indexes],
        'latest_sample_explain':plan,'verified_services':len(counts),'samples_per_service':SAMPLES_PER_SERVICE,
        'postgresql_settings':settings,'network':'loopback, sin limitación artificial',
        'note':'Diagnóstico DB; no aceptación de tiempo de resultado visible'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['init','plan','prepare','serve'])
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--execute',action='store_true',help='Confirma creación de secretos/datos o servicio local')
    args=parser.parse_args()
    if args.command=='plan':
        print(json.dumps({'services':SERVICES,'days':90,'samples':SERVICES*SAMPLES_PER_SERVICE,
            'sessions':{'admin':5,'catedra_admin':5},'database':'nap_perf_009 / loopback:55434',
            'api':f'loopback:{API_PORT}','origin':ORIGIN,'side_effects':'ninguno'})); return
    if not args.execute:
        parser.error('Esta acción requiere --execute; usar plan para inspección sin cambios')
    try:
        if args.command=='init':
            init_private(args.config); return
        config=load_private(args.config); configure(config)
        if args.command=='prepare':
            asyncio.run(prepare(config,args.config.parent))
        else:
            from scripts.rendimiento_server import serve
            serve(config,args.config.parent)
    except (KeyboardInterrupt,Exception) as exc:
        # El tipo permite diagnosticar sin imprimir URLs, contraseñas ni SQL params.
        print(f'Laboratorio no completado ({type(exc).__name__}); revisar configuración/estado aislados',file=sys.stderr)
        raise SystemExit(1) from None


if __name__=='__main__':
    main()
