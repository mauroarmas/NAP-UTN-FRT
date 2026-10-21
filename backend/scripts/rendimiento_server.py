"""API real del laboratorio aislado; sólo los transportes de infraestructura son dobles.

No importar desde app.main ni desplegar este módulo en operación. Los controles
privados no forman parte del producto y no devuelven sesiones ni credenciales.
"""
import asyncio
from contextlib import asynccontextmanager, suppress
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
from zoneinfo import ZoneInfo
import secrets
import time
from uuid import UUID, uuid4

from scripts.validar_carga import API_PORT, ORIGIN, load_private, write_private


def serve(config, directory):
    import uvicorn
    from fastapi import HTTPException, Request
    from sqlalchemy import event, select
    from httpx import ASGITransport, AsyncClient
    from app.config import get_settings
    from app.database import engine, AsyncSessionLocal
    from app.models.definicion_servicio import DefinicionServicio
    from app.models.evidencia import Evidencia
    from app.models.operacion_infraestructura import OperacionInfraestructura
    from app.models.pedido import Pedido, EstadoPedido
    from app.models.recurso_template import RecursoTemplate
    from app.models.usuario import Usuario
    from app.schemas.evidencia import canonical
    from app.schemas.definicion import digest
    from app.utils.clock import clock
    from tests.fakes import FakeProxmoxClient
    from tests.service_helpers import manifest, definition_proof

    fixture=load_private(directory/'fixture.json')
    if fixture['samples'] != 12960000 or fixture['environment'] != 'simulado':
        raise ValueError('Fixture completo simulado requerido')
    control_file=directory/'control.json'
    if not control_file.exists():
        write_private(control_file,{'token':secrets.token_urlsafe(48)})
    control_key=load_private(control_file)['token']
    state={'operation_id':None,'started_monotonic':None,'released':False,'last_worker_error':None}

    class SlowPVE(FakeProxmoxClient):
        def get_task_status(self,node,upid):
            # Una tarea PVE pendiente, no un sleep dentro de la API ni una
            # transacción mantenida treinta segundos. El worker conserva UPID.
            time.sleep(2)
            self.task_polls.append((node,upid))
            return {'status':'stopped','exitstatus':'OK'} if state['released'] else {'status':'running'}

    class Runner:
        async def execute(self,request):
            # Doble de transporte: no conserva stdin/secrets ni usa SSH real.
            return {'protocol':request['protocol'],'operation_id':request['operation_id'],
                'action':request['action'],'resource_uuid':request['resource_uuid'],
                'status':'succeeded','phase':'verified','observed_at':clock.now().isoformat(),
                'identity_verified':True,'result':{'ready':True,'bootstrap_completed':True,
                    'username':'napadmin','addresses':['10.50.0.101'],'checks':['linux-ready-v1']}}

    pve=SlowPVE(next_vmid=5000)
    pve.nodos=[{'node':'pve1','status':'online','maxcpu':4096,'maxmem':8192*1024**3,'mem':1024**3}]
    pve.storages=[{'node':'pve1','storage':'local-lvm','content':'rootdir,images',
        'active':1,'enabled':1,'shared':0,'total':10000*1024**3,'avail':9000*1024**3}]
    pve.contenidos_storage[('pve1','local-lvm')]=[]
    for item in fixture['services']:
        vmid=1000+fixture['services'].index(item)
        pve.recursos.append({'type':'lxc','vmid':vmid,'node':'pve1','status':'running',
            'pool':f"catedra-{item['category_id']}", 'maxcpu':1,'maxmem':512*1024**2})
        pve.configuraciones[('pve1',vmid)]={'cores':1,'memory':512,'rootfs':f'local-lvm:vm-{vmid}-disk-0,size=4G'}
        pve.contenidos_storage[('pve1','local-lvm')].append({'volid':f'local-lvm:vm-{vmid}-disk-0','size':4*1024**3,'content':'rootdir'})
    # Inyección exclusivamente en el transporte, antes de cargar los routers.
    from app.services import proxmox_client
    proxmox_client.get_proxmox_factory=lambda:lambda:pve
    proxmox_client.get_proxmox_client=lambda:pve
    from app.main import app
    from app.worker import procesar_una

    stats_context=ContextVar('perf_sql',default=None)
    @event.listens_for(engine.sync_engine,'before_cursor_execute')
    def before(conn,cursor,statement,parameters,context,many):
        context._perf_start=time.perf_counter()
    @event.listens_for(engine.sync_engine,'after_cursor_execute')
    def after(conn,cursor,statement,parameters,context,many):
        stats=stats_context.get()
        if stats is not None:
            stats['count']+=1; stats['seconds']+=time.perf_counter()-context._perf_start

    @app.middleware('http')
    async def diagnostic(request,call_next):
        stats={'count':0,'seconds':0.0}; token=stats_context.set(stats); start=time.perf_counter()
        try:
            response=await call_next(request)
            response.headers['Server-Timing']=f"http;dur={(time.perf_counter()-start)*1000:.3f}, db;dur={stats['seconds']*1000:.3f}, queries;desc=\"{stats['count']}\""
            if request.url.path.startswith('/api/'):
                response.headers['Cache-Control']='no-store'
            return response
        finally:
            stats_context.reset(token)

    async def setup_definition():
        settings=get_settings()
        settings.infrastructure_profile={'version':1,'cluster_id':fixture['cluster_uuid'],
            'nodos':{'pve1':{'margen_vcpus':1,'margen_ram_mb':512,'storages':['local-lvm']}},
            'almacenamientos':{'local-lvm':{'shared':False,'margen_logico_bytes':0,'margen_fisico_bytes':0}}}
        image,bundle=directory/'imagen-sintetica.txt',directory/'receta-sintetica.txt'
        for path,label in [(image,'imagen'),(bundle,'receta')]:
            if not path.exists():
                fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o444)
                with os.fdopen(fd,'w') as output: output.write(f'SIMULADO-SC008-{label}\n')
        async with AsyncSessionLocal() as db:
            definition=await db.scalar(select(DefinicionServicio).where(DefinicionServicio.codigo=='linux-rendimiento-simulado'))
            if definition is None:
                value=manifest('linux'); identity,reference=uuid4(),uuid4()
                value['definition_key']='linux-rendimiento-simulado'
                value['image']['sha256']=hashlib.sha256(image.read_bytes()).hexdigest()
                value['preparation']['bundle_sha256']=hashlib.sha256(bundle.read_bytes()).hexdigest()
                value['validation']['cluster_uuid']=fixture['cluster_uuid']
                proof=definition_proof(identity,value); proof.update(entorno='simulado',
                    operador_institucional='generador-SC008',referencia_institucional='SIN-ACEPTACION-INSTITUCIONAL')
                encoded=canonical(proof); checksum=hashlib.sha256(encoded.encode()).hexdigest()
                db.add(Evidencia(id=reference,tipo='validacion_definicion',schema_version=1,
                    documento_canonico=encoded,sha256=checksum,registrada_por=fixture['users'][0]['id']))
                await db.flush()
                value['validation'].update(evidence_id=str(reference),evidence_sha256=checksum)
                # Fixture de oferta sólo dentro de app_env=test/DB marcada.
                # No usa ni publica ninguna imagen de los ensayos reales T101.
                definition=DefinicionServicio(id=identity,codigo=value['definition_key'],version='1.0.0',
                    producto='linux',modelo_servicio='iaas',manifest=value,manifest_sha256=digest(value),
                    estado='publicada',validada_por=fixture['users'][0]['id'],validada_at=clock.now(),evidencia_validacion=reference)
                db.add(definition)
                await db.flush()
                db.add(RecursoTemplate(nombre='Linux SC008 simulado',modelo_servicio='iaas',
                    default_vcpus=1,default_ram_mb=512,default_disk_gb=4,activo=True,
                    os_template=value['image']['volume_id'],definicion_version_id=definition.id))
                await db.commit()
            value=definition.manifest
        settings.service_artifacts={value['definition_key']+':1.0.0':{'image_path':str(image),
            'bundle_path':str(bundle),'nodes':['pve1'],'network_profile_id':'test-network'}}
        settings.runner_nodes={'pve1':{'simulado':True}}
        settings.network_profiles={'test-network':{'bridge':'vmbr0','nodes':['pve1'],
            'allowed_cidrs':['10.50.0.0/24'],'client_cidrs':['10.50.0.0/24']}}
        pve.contenidos_storage[('pve1','local')]=[{'volid':value['image']['volume_id'],'content':'vztmpl','size':image.stat().st_size}]

    async def worker():
        while True:
            try:
                await procesar_una(AsyncSessionLocal,pve=pve,runner=Runner())
            except Exception as exc:
                state['last_worker_error']=type(exc).__name__
            await asyncio.sleep(1)

    original_lifespan=app.router.lifespan_context
    @asynccontextmanager
    async def lifespan(application):
        async with original_lifespan(application):
            await setup_definition()
            task=asyncio.create_task(worker())
            try: yield
            finally:
                task.cancel()
                with suppress(asyncio.CancelledError): await task
                await engine.dispose()
    app.router.lifespan_context=lifespan

    def authorize(request):
        if not hmac.compare_digest(request.headers.get('x-performance-control',''),control_key):
            raise HTTPException(403,'Control privado del ensayo')

    async def public_state():
        async with AsyncSessionLocal() as db:
            op=await db.get(OperacionInfraestructura,UUID(state['operation_id'])) if state['operation_id'] else None
            return {'operation_id':state['operation_id'],'estado':op.estado if op else None,
                'fase':op.fase if op else None,'error_codigo':op.error_codigo if op else None,
                'pending_seconds':time.monotonic()-state['started_monotonic'] if state['started_monotonic'] else 0,
                'released':state['released'],'worker_error':state['last_worker_error'],
                'pve_polls':len(pve.task_polls),'simulado':True}

    @app.get('/__performance/state',include_in_schema=False)
    async def get_state(request:Request):
        authorize(request); return await public_state()

    @app.post('/__performance/start',include_in_schema=False)
    async def start(request:Request):
        authorize(request)
        if state['operation_id']:
            return await public_state()
        async with AsyncSessionLocal() as db:
            template=await db.scalar(select(RecursoTemplate).where(RecursoTemplate.nombre=='Linux SC008 simulado'))
            user=fixture['users'][5]; category=fixture['services'][0]['category_id']
            pedido=Pedido(catedra_id=category,solicitante_id=user['id'],template_id=template.id,
                modelo_servicio='iaas',estado=EstadoPedido.SOLICITADO,
                descripcion_requerimientos='Despliegue lento SIMULADO para SC008')
            db.add(pedido); await db.commit(); pedido_id=pedido.id; template_id=template.id
            definition_id=str(template.definicion_version_id)
        # Login/CSRF/evaluación/aprobación/202 reales, sin sustituir el negocio.
        credentials=config['users'][0]
        async with AsyncClient(transport=ASGITransport(app=app),base_url='https://localhost',
                headers={'Origin':ORIGIN,'X-NAP-Request':'1'}) as client:
            response=await client.post('/api/v1/auth/login',data={'username':credentials['username'],'password':credentials['password']})
            if response.status_code!=200: raise HTTPException(500,'Login interno del ensayo falló')
            csrf=await client.get('/api/v1/auth/csrf')
            if csrf.status_code!=200: raise HTTPException(500,'CSRF interno del ensayo falló')
            client.headers['X-CSRF-Token']=csrf.json()['csrf_token']
            today=clock.now().astimezone(ZoneInfo('America/Argentina/Tucuman')).date()
            payload={'asignacion':{'template_id':template_id,'definicion_version_id':definition_id,'vcpus':1,'ram_mb':512,'disk_gb':4},
                'destino':{'nodo':'pve1','storage':'local-lvm'},
                'vigencia':{'tipo':'personalizado','desde':today.isoformat(),'hasta':(today+timedelta(days=10)).isoformat()}}
            evaluated=await client.post(f'/api/v1/pedidos/{pedido_id}/evaluacion',json=payload)
            if evaluated.status_code!=200: raise HTTPException(500,{'stage':'evaluacion','status':evaluated.status_code,'code':evaluated.json().get('detail',{}).get('codigo')})
            approved=await client.post(f'/api/v1/pedidos/{pedido_id}/aprobar',json=payload|{'capacidad_token':evaluated.json()['capacidad_token']},headers={'Idempotency-Key':'perf-approve-'+str(pedido_id)})
            if approved.status_code!=200: raise HTTPException(500,{'stage':'aprobar','status':approved.status_code})
            deployed=await client.post(f'/api/v1/servicios/desplegar/{pedido_id}',json={},headers={'Idempotency-Key':'perf-deploy-'+str(pedido_id)})
            if deployed.status_code!=202: raise HTTPException(500,{'stage':'desplegar','status':deployed.status_code})
            state.update(operation_id=deployed.json()['operation_id'],started_monotonic=time.monotonic())
        return (await public_state())|{'accepted_status':202}

    @app.post('/__performance/finish',include_in_schema=False)
    async def finish(request:Request):
        authorize(request)
        if not state['started_monotonic'] or time.monotonic()-state['started_monotonic']<30:
            raise HTTPException(409,'El despliegue debe permanecer pendiente al menos treinta segundos')
        state['released']=True
        # Espera sólo del control de ensayo; las consultas siguen atendidas.
        for _ in range(60):
            current=await public_state()
            if current['estado'] in {'confirmada','fallida','incierta'}:
                return current
            await asyncio.sleep(1)
        raise HTTPException(504,'El worker no confirmó el cierre del ensayo')

    uvicorn.run(app,host='127.0.0.1',port=API_PORT,access_log=False,log_level='warning')
