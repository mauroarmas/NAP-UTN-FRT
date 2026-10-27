from datetime import timedelta
from uuid import uuid4
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from app.config import get_settings
from app.schemas.biblioteca_config import BuilderHost,PerfilEnsayo
from app.models.operacion_ensayo import OperacionEnsayo
from app.services import ensayo_service,ensayo_worker
from app.utils.clock import clock
from tests.test_ensayo_limpieza_010 import make_trial


async def test_lease_se_renueva_durante_io_largo_pero_no_despues_de_cancelar(db,engine,admin):
    from app.utils.clock import db_utc
    trial=await make_trial(db,admin)
    ensayo_service.enqueue(db,trial,kind='resolver');await db.commit()
    lease=await ensayo_worker.claim(db,uuid4());await db.commit()
    op=await db.get(OperacionEnsayo,lease[0]);op.lease_until=clock.now()+timedelta(seconds=2);await db.commit()
    sessions=async_sessionmaker(engine,expire_on_commit=False)
    assert await ensayo_worker.renovar_lease(sessions,lease)
    await db.refresh(op)
    assert db_utc(op.lease_until)>clock.now()+timedelta(seconds=80)
    trial.cancelada_at=clock.now();await db.commit()
    assert not await ensayo_worker.renovar_lease(sessions,lease)


class Builder:
    def __init__(self,entries):self.entries=entries;self.calls=[];self.lost=False;self.jobs={}
    async def execute(self,request,*,host_id):
        self.calls.append(request)
        key=request['operation_id']
        result=self.jobs.setdefault(key,{'protocol':'nap-build-runner/1','operation_id':key,'generation':request['generation'],
            'status':'succeeded','result':{'entradas_resueltas':self.entries,'input_ref':'b'*64,'input_sha256':'b'*64}})
        if self.lost:self.lost=False;raise TimeoutError()
        return result


def config(monkeypatch):
    monkeypatch.setattr(get_settings(),'builder_hosts',{'builder':BuilderHost(host='builder.example.edu',user='builder',private_key_path='/run/key',known_hosts_path='/run/known',scope_id='scope-prueba',limit_bytes=100,job_bytes=50)})
    monkeypatch.setattr(get_settings(),'perfiles_ensayo',{'prueba':PerfilEnsayo(builder_id='builder',nodo='pve1',storage='local-lvm',pool='ensayos',network_profile_id='red-prueba',vcpus=1,ram_mb=512,disk_gb=4)})


async def test_confirmacion_perdida_consulta_job_sin_otro_build(db,engine,admin,monkeypatch):
    config(monkeypatch)
    trial=await make_trial(db,admin)
    op=ensayo_service.enqueue(db,trial,kind='resolver',context={'recipe_revision':'a'*40,'input_ref':'catalogo','input_sha256':'b'*64})
    await db.flush();oid=op.id;tid=trial.id
    entries={'base_sha256':'c'*64,'package_lock':{'base':'1.0'},'runtime':{'packages':[],'components':{}},
        'recipe_revision':'a'*40,'definition_id':str(trial.definicion_id),'definition_key':'drawio-trial','definition_version':'1.0.0'}
    builder=Builder(entries);builder.lost=True
    await db.commit();sessions=async_sessionmaker(engine,expire_on_commit=False)
    assert await ensayo_worker.procesar_una(sessions,builder=builder)
    await db.refresh(trial);await db.refresh(op)
    assert trial.estado=='incierta' and op.estado=='incierta'
    op.next_poll_at=clock.now();await db.commit()
    assert await ensayo_worker.procesar_una(sessions,builder=builder)
    await db.refresh(trial)
    assert trial.estado=='esperando_confirmacion'
    assert [r['action'] for r in builder.calls]==['resolve','status']
    assert len(builder.jobs)==1


async def test_lease_antiguo_no_confirma_resultado(db,engine,admin,monkeypatch):
    config(monkeypatch)
    trial=await make_trial(db,admin);ensayo_service.enqueue(db,trial,kind='resolver',context={});await db.commit()
    lease=await ensayo_worker.claim(db,uuid4());await db.commit()
    op=await db.get(OperacionEnsayo,lease[0]);op.lease_until=clock.now()-timedelta(seconds=1);await db.commit()
    newer=await ensayo_worker.claim(db,uuid4());await db.commit()
    assert newer[2]>lease[2]
    import pytest
    with pytest.raises(RuntimeError):await ensayo_worker.owned(db,lease)
