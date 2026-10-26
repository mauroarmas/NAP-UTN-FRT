"""Pipeline con transportes simulados; no acredita aceptación real."""
from copy import deepcopy
import pytest
from uuid import uuid4,UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from app.config import get_settings
from app.models.definicion_servicio import DefinicionServicio
from app.models.operacion_ensayo import OperacionEnsayo
from app.models.compromiso_capacidad import CompromisoCapacidad
from app.models.reserva_espacio_builder import ReservaEspacioBuilder
from app.schemas.ensayo import EnsayoCreate,ConfirmarEntradas,DescartarEnsayo
from app.schemas.definicion import digest
from app.schemas.biblioteca_config import BuilderHost
from app.services import ensayo_service,ensayo_worker,ensayo_cleanup_service
from app.utils.clock import clock
from tests.test_ensayo_limpieza_010 import make_trial
from tests.test_ensayo_worker_010 import config
from tests.test_drawio_entrega_010 import DrawRunner
from tests.drawio_helpers import drawio_manifest
from tests.capacity_helpers import perfil_capacidad


class PipelineBuilder:
    def __init__(self,manifest):self.manifest=manifest;self.calls=[];self.closed=False;self.fail_cleanup=False
    async def execute(self,request,*,host_id):
        self.calls.append(deepcopy(request));action=request['action'];result={}
        if action=='status':result={'free_bytes':10000,'recipe_ready':True,'recipe_revision':'a'*40,'input_ref':'catalogo','input_sha256':'b'*64}
        elif action=='resolve':
            result={'input_ref':'b'*64,'input_sha256':'b'*64,'entradas_resueltas':{'base_sha256':'c'*64,
                'package_lock':{'base':'1.0'},'runtime':self.manifest['runtime'],'recipe_revision':'a'*40,
                'definition_id':request['definition_id'],'definition_key':request['definition_key'],'definition_version':request['definition_version']}}
        elif action=='build':result={'manifest':self.manifest,'image_bytes':10,'bundle_bytes':10,'saneamiento':{'builder_sanitized':True}}
        elif action=='stage':result={'replicas':[{'nodo':'pve1','storage_id':'local','image_sha256':self.manifest['image']['sha256'],
            'bundle_sha256':self.manifest['preparation']['bundle_sha256'],'registro_revision':digest(request.get('validated_manifest',self.manifest))}]}
        elif action=='cancel':self.closed=True
        elif action=='cleanup':
            assert self.closed
            if self.fail_cleanup:raise TimeoutError('cleanup_uncertain')
        return {'status':'cancelled' if action=='cancel' else 'succeeded','closed':self.closed,'result':result}


@pytest.mark.parametrize('lost_create_response',[False,True])
@pytest.mark.parametrize('task_exitstatus',['OK','WARNINGS: 1'])
async def test_pipeline_dos_recursos_descarta_y_retiene_hasta_cleanup_confirmado(db,engine,admin,proxmox,perfil_capacidad,monkeypatch,lost_create_response,task_exitstatus):
    original_status=proxmox.get_task_status
    def task_status(*args,**kwargs):
        result=original_status(*args,**kwargs)
        return {**result,'exitstatus':task_exitstatus} if result.get('status')=='stopped' else result
    monkeypatch.setattr(proxmox,'get_task_status',task_status)
    config(monkeypatch);settings=get_settings()
    monkeypatch.setattr(settings,'builder_hosts',{'builder':BuilderHost(host='builder.example.edu',user='builder',private_key_path='/run/key',known_hosts_path='/run/known',scope_id='scope-prueba',limit_bytes=10000,job_bytes=5000)})
    seed=await make_trial(db,admin);definition=await db.get(DefinicionServicio,seed.definicion_id)
    definition.incorporacion_id=seed.incorporacion_id
    inc=seed.incorporacion_id;did=definition.id
    await db.delete(seed);await db.commit()
    manifest=drawio_manifest();builder=PipelineBuilder(manifest);runner=DrawRunner()
    if lost_create_response:
        original=proxmox.create_lxc;lost=[False]
        def lose_once(*args,**kwargs):
            value=original(*args,**kwargs)
            if not lost[0]:lost[0]=True;raise TimeoutError('confirmation lost after create')
            return value
        monkeypatch.setattr(proxmox,'create_lxc',lose_once)
    perfil_capacidad['cluster_id']=manifest['validation']['cluster_uuid'];proxmox.pools['ensayos']=[]
    instances={str(uuid4()):{'host':f'ensayo-{n}.example.edu','address':f'10.50.0.{101+n}','mac_address':f'02:00:00:00:00:0{n+1}','products':['drawio']} for n in range(2)}
    monkeypatch.setattr(settings,'network_profiles',{'red-prueba':{'bridge':'vmbr0','nodes':['pve1'],'allowed_cidrs':['10.50.0.0/24'],'client_cidrs':['10.50.0.0/24'],'instances':instances}})
    result=await ensayo_service.iniciar(db,did,actor=admin,data=EnsayoCreate(incorporacion_id=inc,revision_esperada=1,perfil_ensayo_id='prueba',plazo_horas=24),clave='pipeline-start',pve=proxmox,builder=builder)
    assert result.status_code==202
    tid=UUID(result.resultado['id'])
    await db.commit();sessions=async_sessionmaker(engine,expire_on_commit=False)
    assert await ensayo_worker.procesar_una(sessions,builder=builder,pve=proxmox,runner=runner)
    trial=await ensayo_service.obtener(db,tid);assert trial.estado=='esperando_confirmacion'
    await ensayo_service.accion(db,tid,actor=admin,data=ConfirmarEntradas(revision_esperada=trial.revision,entradas_sha256=trial.entradas_sha256),clave='pipeline-confirm',action='confirmar-entradas');await db.commit()
    for _ in range(14):
        operations=(await db.scalars(select(OperacionEnsayo).where(OperacionEnsayo.ensayo_id==tid))).all()
        for operation in operations:operation.next_poll_at=clock.now()
        await db.commit()
        await ensayo_worker.procesar_una(sessions,builder=builder,pve=proxmox,runner=runner)
        trial=await ensayo_service.obtener(db,tid)
        if trial.estado=='lista_para_comprobar':break
        assert trial.estado!='incierta' or lost_create_response,[(o.tipo,o.error_codigo) for o in operations]
        await db.commit()
    assert trial.estado=='lista_para_comprobar'
    assert len(proxmox.creados)==2 and len(runner.requests)==2
    assert runner.requests[0]['secrets']!=runner.requests[1]['secrets']
    await ensayo_service.accion(db,tid,actor=admin,data=DescartarEnsayo(revision_esperada=trial.revision,motivo='Finalizar prueba'),clave='pipeline-discard',action='descartar');await db.commit()
    builder.fail_cleanup=True
    for _ in range(20):
        await ensayo_cleanup_service.procesar(sessions,builder=builder,pve=proxmox)
        trial=await ensayo_service.obtener(db,tid);await db.commit()
        if trial.limpieza_estado=='fallida':break
    assert trial.limpieza_estado=='fallida' and trial.artefacto_id
    reservation=await db.scalar(select(ReservaEspacioBuilder).where(ReservaEspacioBuilder.ensayo_id==tid));assert reservation.liberado_at is None
    assert builder.closed and len(proxmox.eliminados)==2
    from app.schemas.biblioteca_common import RevisionEsperada
    await ensayo_service.accion(db,tid,actor=admin,data=RevisionEsperada(revision_esperada=trial.revision),clave='pipeline-cleanup-retry',action='reintentar-limpieza');await db.commit()
    builder.fail_cleanup=False;await ensayo_cleanup_service.procesar(sessions,builder=builder,pve=proxmox)
    trial=await ensayo_service.obtener(db,tid);await db.refresh(reservation)
    assert trial.limpieza_estado=='confirmada' and reservation.liberado_at
    ledgers=(await db.scalars(select(CompromisoCapacidad).where(CompromisoCapacidad.recurso_ensayo_id.is_not(None)))).all()
    assert len(ledgers)==2 and all(l.liberado_at for l in ledgers)
