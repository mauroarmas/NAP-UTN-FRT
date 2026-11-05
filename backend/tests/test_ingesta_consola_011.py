from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

from fastapi import HTTPException
import pytest
from sqlalchemy import select,func
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.consola_operacion import ConsolaOperacion,ConsolaFragmento
from app.models.identidad_infraestructura import IdentidadInfraestructura
from app.models.intento_despliegue import IntentoDespliegue
from app.models.operacion_infraestructura import OperacionInfraestructura
from app.services.operacion_service import LeaseOperacion
from app.utils.clock import clock
from infra.applications.job.protocol import public_identity


@pytest.fixture
async def console_job(db):
    identity=IdentidadInfraestructura(cluster_id=str(uuid4()),nodo='pve1',vmid=501,
        pool_catedra='nap-apps',nonce_cifrado='fixture-not-used-by-console')
    db.add(identity);await db.flush()
    owner=uuid4()
    operation=OperacionInfraestructura(tipo='desplegar',identidad_infraestructura_id=identity.id,
        actor_tipo='sistema',actor_id_normalizado='fixture',idempotency_key=str(uuid4()),request_hash='a'*64,
        estado='en_curso',lease_owner=owner,lease_generation=1,lease_until=clock.now()+timedelta(minutes=2),
        contexto_seguro={'job_fingerprint':'f'*64})
    db.add(operation);await db.flush()
    attempt=IntentoDespliegue(operacion_id=operation.id,operacion_raiz_id=operation.id,
        numero=1,identidad_infraestructura_id=identity.id,configuracion_sha256='b'*64)
    db.add(attempt);await db.commit()
    request={'protocol':'nap-application-job/1','action':'read','operation_id':str(operation.id),
        'operacion_raiz_id':str(operation.id),'intento_id':str(attempt.id),'execution_id':str(attempt.execution_id),
        'lease_generation':1,'cluster_uuid':identity.cluster_id,'node':identity.nodo,'vmid':identity.vmid,
        'resource_uuid':str(identity.resource_uuid),'pool':identity.pool_catedra,'nonce':'e'*64,
        'configuracion_sha256':'b'*64,'perfil':{'id':'docker-ubuntu24','revision':1,'sha256':'a'*64},
        'after':0,'limit_bytes':65536}
    return SimpleNamespace(identity=identity,operation=operation,attempt=attempt,request=request,
        lease=LeaseOperacion(operation.id,owner,1),boot=str(uuid4()))


def batch(job, sequences=(1,2), *, state='ejecutando', dropped=()):
    return {'protocol':'nap-application-job/1','ok':True,'action':'read','data':{
        **public_identity(job.request),'fingerprint':'f'*64,'node_boot_id':job.boot,
        'estado':state,'fase':'instalacion','last_source_seq':max([*sequences,*(v['through_seq'] for v in dropped)],default=0),
        'acknowledged_seq':0,'resultado':None,'error_codigo':None,
        'items':[{'execution_id':str(job.attempt.execution_id),'source_seq':n,
            'captured_at':clock.now().isoformat().replace('+00:00','Z'),'fase':'instalacion','stream':'stdout',
            'texto_depurado':f'Paquete instalado: paso-{n}.'} for n in sequences],
        'dropped_ranges':list(dropped)}}


async def fragments(db):return list((await db.scalars(select(ConsolaFragmento).order_by(ConsolaFragmento.seq))).all())


async def test_portal_and_runner_keys_do_not_collide_and_replay_is_idempotent(db,console_job):
    from app.services.consola_operacion_service import emitir_hito,ingerir
    job=console_job
    await emitir_hito(db,job.lease,hito='creando_recurso')
    await db.commit()
    assert job.operation.fase=='creacion'
    result=await ingerir(db,job.lease,request=job.request,response=batch(job));await db.commit()
    assert result['through_seq']==2
    await emitir_hito(db,job.lease,hito='creando_recurso')
    await ingerir(db,job.lease,request=job.request,response=batch(job));await db.commit()
    rows=await fragments(db)
    assert [r.seq for r in rows]==[1,2,3] and [r.source for r in rows]==['portal','runner','runner']
    assert [r.source_key for r in rows[1:]]==['1','2']
    assert job.attempt.ultimo_source_seq==2


async def test_failed_creation_without_node_job_keeps_header_phase_and_final_result(db,console_job):
    from app.services.consola_operacion_service import emitir_hito
    job=console_job
    await emitir_hito(db,job.lease,hito='creando_recurso')
    await emitir_hito(db,job.lease,hito='fallo');await db.commit()
    header=await db.get(ConsolaOperacion,job.operation.id)
    assert header.ultimo_resultado_seguro=={'hito':'fallo','texto':'No se pudo completar el despliegue.'}
    assert job.operation.fase=='finalizada' and job.attempt.runner_job_id is None
    assert len(await fragments(db))==2


async def test_phase_event_and_cursor_are_rolled_back_together(db,console_job):
    from app.services.consola_operacion_service import emitir_hito,ingerir
    job=console_job;operation_id=job.operation.id;attempt_id=job.attempt.id
    await emitir_hito(db,job.lease,hito='creando_recurso')
    await ingerir(db,job.lease,request=job.request,response=batch(job));await db.rollback()
    assert not await fragments(db)
    op=await db.get(OperacionInfraestructura,operation_id);attempt=await db.get(IntentoDespliegue,attempt_id)
    assert op.fase=='preparacion' and attempt.ultimo_source_seq==0


@pytest.mark.parametrize('bad',['identity','lease','gap','extra','fingerprint','cursor','control'])
async def test_invalid_or_stale_batch_never_advances_cursor_or_persists_raw_text(db,console_job,bad):
    from app.services.consola_operacion_service import ingerir
    job=console_job;page=batch(job)
    lease=job.lease
    if bad=='identity':page['data']['resource_uuid']=str(uuid4())
    if bad=='lease':lease=LeaseOperacion(lease.id,uuid4(),lease.generation)
    if bad=='gap':page=batch(job,sequences=(2,))
    if bad=='extra':page['data']['password']='private-batch-must-never-persist'
    if bad=='fingerprint':page['data']['fingerprint']='c'*64
    if bad=='cursor':page['data']['acknowledged_seq']=2;page['data']['items']=[]
    if bad=='control':page['data']['items'][0]['texto_depurado']='\x1b[31mprivate-batch-must-never-persist'
    with pytest.raises(HTTPException) as caught:await ingerir(db,lease,request=job.request,response=page)
    await db.rollback()
    assert not await fragments(db) and 'private-batch' not in str(caught.value.detail)


async def test_explicit_node_loss_can_advance_but_unexplained_gap_cannot(db,console_job):
    from app.services.consola_operacion_service import ingerir
    job=console_job
    page=batch(job,sequences=(4,5),dropped=[{'from_seq':1,'through_seq':3,'bytes':70}])
    result=await ingerir(db,job.lease,request=job.request,response=page);await db.commit()
    assert result['through_seq']==5
    rows=await fragments(db);header=await db.get(ConsolaOperacion,job.operation.id)
    assert rows[0].source=='portal' and '3 mensajes' in rows[0].texto_depurado
    assert [r.source_seq for r in rows[1:]]==[4,5] and header.dropped_messages==3 and header.truncated
    await ingerir(db,job.lease,request=job.request,response=page);await db.commit()
    assert len(await fragments(db))==3 and header.dropped_messages==3


async def test_final_portal_event_waits_for_all_fragments_of_finished_node_job(db,console_job):
    from app.services.consola_operacion_service import emitir_hito,ingerir
    job=console_job;page=batch(job,sequences=(1,),state='confirmado');page['data']['last_source_seq']=2
    page['data']['resultado']={'comprobaciones':['aislamiento','runtime','salud','acceso_web'],'recurso_configurado':True}
    await ingerir(db,job.lease,request=job.request,response=page);await db.commit()
    with pytest.raises(HTTPException):await emitir_hito(db,job.lease,hito='disponible')
    page=batch(job,sequences=(2,),state='confirmado');page['data']['resultado']={'comprobaciones':['aislamiento','runtime','salud','acceso_web'],'recurso_configurado':True}
    await ingerir(db,job.lease,request=job.request,response=page)
    await emitir_hito(db,job.lease,hito='disponible');await db.commit()
    assert [r.source for r in await fragments(db)]==['runner','runner','portal']


async def test_retention_preserves_cursor_final_result_and_replay_tombstones(db,console_job,monkeypatch):
    from app.services.consola_operacion_service import emitir_hito,ingerir,purgar
    job=console_job
    await emitir_hito(db,job.lease,hito='creando_recurso')
    await ingerir(db,job.lease,request=job.request,response=batch(job,state='fallido'))
    await emitir_hito(db,job.lease,hito='fallo');await db.commit()
    future=clock.now()+timedelta(days=31);monkeypatch.setattr(clock,'now',lambda:future)
    await purgar(db,job.operation.id);await db.commit()
    header=await db.get(ConsolaOperacion,job.operation.id)
    assert not await fragments(db) and header.expired and header.last_seq==4 and header.retained_bytes==0
    assert header.ultimo_resultado_seguro['hito']=='fallo'
    job.operation.lease_until=future+timedelta(minutes=1);await db.commit()
    await emitir_hito(db,job.lease,hito='creando_recurso')
    await ingerir(db,job.lease,request=job.request,response=batch(job,state='fallido'));await db.commit()
    assert not await fragments(db) and header.last_seq==4


async def test_ack_is_sent_only_after_database_commit_and_lost_ack_replays_without_duplicates(engine,db,console_job):
    from app.services.consola_operacion_service import ingerir_y_confirmar
    job=console_job;sessions=async_sessionmaker(engine,expire_on_commit=False);calls=[]
    class Client:
        async def execute(self,request,**kwargs):
            async with sessions() as reader:
                assert await reader.scalar(select(func.count()).select_from(ConsolaFragmento))==2
            calls.append(request)
            raise TimeoutError('private transport message')
    result=await ingerir_y_confirmar(sessions,job.lease,request=job.request,response=batch(job),client=Client())
    assert result['ack_confirmed'] is False and calls[0]['action']=='ack' and calls[0]['through_seq']==2
    await ingerir_y_confirmar(sessions,job.lease,request=job.request,response=batch(job),client=Client())
    assert len(await fragments(db))==2


async def test_database_commit_failure_never_sends_ack(engine,db,console_job):
    from app.services.consola_operacion_service import ingerir_y_confirmar
    # The transaction context commits its transaction object, so inject at the
    # synchronous before_commit boundary rather than overriding Session.commit.
    from sqlalchemy import event
    sessions=async_sessionmaker(engine,expire_on_commit=False)
    calls=[]
    class Client:
        async def execute(self,*args,**kwargs):calls.append(args);raise AssertionError('ACK before durable commit')
    from sqlalchemy.orm import Session
    def reject(_):raise RuntimeError('fixture commit rejected')
    event.listen(Session,'before_commit',reject)
    try:
        with pytest.raises(RuntimeError,match='commit rejected'):
            await ingerir_y_confirmar(sessions,console_job.lease,request=console_job.request,
                response=batch(console_job),client=Client())
    finally:event.remove(Session,'before_commit',reject)
    assert not calls and not await fragments(db)


async def test_quota_and_expiry_keep_replay_cursors_when_text_is_removed(db,console_job,monkeypatch):
    from app.services import consola_operacion_service as service
    monkeypatch.setattr(service,'MAX_BYTES',60)
    job=console_job;page=batch(job,sequences=(1,2,3,4))
    for item in page['data']['items']:item['texto_depurado']='ñ'*20
    await service.ingerir(db,job.lease,request=job.request,response=page);await db.commit()
    header=await db.get(ConsolaOperacion,job.operation.id)
    assert header.retained_bytes==40 and header.dropped_bytes==120 and header.dropped_messages==3
    assert header.first_retained_seq==4 and header.last_seq==4
    await service.ingerir(db,job.lease,request=job.request,response=page);await db.commit()
    assert [r.seq for r in await fragments(db)]==[4] and header.last_seq==4


async def test_portal_does_not_announce_success_without_a_confirmed_node_or_regress_phase(db,console_job):
    from app.services.consola_operacion_service import emitir_hito
    with pytest.raises(HTTPException):await emitir_hito(db,console_job.lease,hito='disponible')
    await emitir_hito(db,console_job.lease,hito='comprobando')
    with pytest.raises(HTTPException):await emitir_hito(db,console_job.lease,hito='creando_recurso')
