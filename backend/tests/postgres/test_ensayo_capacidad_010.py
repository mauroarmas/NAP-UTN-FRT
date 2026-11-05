import asyncio
from uuid import uuid4
import pytest
from sqlalchemy import select,func
from fastapi import HTTPException
from app.models.presupuesto_builder import PresupuestoBuilder
from app.models.reserva_espacio_builder import ReservaEspacioBuilder
from app.models.ensayo_preparacion import EnsayoPreparacion
from app.models.definicion_servicio import DefinicionServicio
from app.models.incorporacion_aplicacion import IncorporacionAplicacion
from app.schemas.biblioteca_config import BuilderHost
from app.services import builder_capacity_service
from app.utils.clock import clock
from datetime import timedelta
from tests.fakes_biblioteca import DRAWIO
from tests import factories
from app.models.usuario import RolUsuario


async def test_primera_reserva_builder_serializa_scope_compartido(pg_sessions):
    host=BuilderHost(host='builder.example.edu',user='builder',private_key_path='/run/key',known_hosts_path='/run/known',scope_id='disco-compartido',limit_bytes=100,job_bytes=70)
    async with pg_sessions() as db:
        user=await factories.crear_usuario(db,'admin-cap-builder',rol=RolUsuario.ADMIN)
        inc=IncorporacionAplicacion(**{k:DRAWIO[k] for k in ['identidad_externa','revision_fuente','comando_sha256','comando_origen','url_origen','nombre','descripcion','categorias','aliases']},origen_clave='desconocida',creado_por=user.id)
        db.add(inc);await db.flush()
        ids=[]
        for n in range(2):
            definition=DefinicionServicio(codigo=f'drawio-presupuesto-{n}',version='1.0.0',producto='drawio',modelo_servicio='saas',manifest={})
            db.add(definition);await db.flush()
            trial=EnsayoPreparacion(incorporacion_id=inc.id,definicion_id=definition.id,perfil_id='prueba',creado_por=user.id,expires_at=clock.now()+timedelta(hours=1),aviso_at=clock.now())
            db.add(trial);await db.flush();ids.append(trial.id)
        await db.commit()
    barrier=asyncio.Barrier(2)
    async def reserve(i):
        async with pg_sessions() as db:
            await barrier.wait()
            try:
                await builder_capacity_service.reservar(db,ensayo_id=ids[i],host_id=f'host-{i}',host=host,free_bytes=100)
                await db.commit();return 201
            except HTTPException as exc:
                await db.rollback();return exc.status_code
    assert sorted(await asyncio.gather(reserve(0),reserve(1)))==[201,409]
    async with pg_sessions() as db:
        assert await db.scalar(select(func.count()).select_from(PresupuestoBuilder))==1
        assert await db.scalar(select(func.count()).select_from(ReservaEspacioBuilder))==1


@pytest.mark.parametrize('competitor',['ensayo','aprobacion'])
async def test_ensayo_compite_por_capacidad_atomica(db,pg_sessions,admin,catedra,usuario_catedra,template,proxmox,monkeypatch,competitor):
    from tests.capacity_helpers import seleccion,preparar_pedido
    from tests.test_ensayo_worker_010 import config
    from tests.test_ensayo_limpieza_010 import make_trial
    from tests.test_ensayo_pipeline_010 import PipelineBuilder
    from tests.drawio_helpers import drawio_manifest
    from app.config import get_settings
    from app.models.usuario import Usuario
    from app.models.compromiso_capacidad import CompromisoCapacidad
    from app.schemas.ensayo import EnsayoCreate
    from app.services import ensayo_service,evaluacion_service,admision_service
    from tests.service_helpers import link_capacity_definition
    definition=await link_capacity_definition(db,template,admin)
    # Dos recursos de 1 vCPU agotan el saldo total de 2 vCPU.
    settings=get_settings();config(monkeypatch)
    monkeypatch.setattr(settings,'infrastructure_profile',{'version':1,'cluster_id':definition['validation']['cluster_uuid'],
        'nodos':{'pve1':{'margen_vcpus':1,'margen_ram_mb':512,'storages':['local-lvm']}},
        'almacenamientos':{'local-lvm':{'shared':False,'margen_logico_bytes':0,'margen_fisico_bytes':0}}})
    proxmox.nodos=[{'node':'pve1','status':'online','maxcpu':3,'maxmem':16*1024**3,'mem':1024**3}]
    proxmox.storages=[{'node':'pve1','storage':'local-lvm','content':'rootdir,images','active':1,'enabled':1,'shared':0,'total':100*1024**3,'avail':100*1024**3}]
    proxmox.contenidos_storage[('pve1','local')]=[{'volid':definition['image']['volume_id'],'content':'vztmpl'}]
    from app.schemas.biblioteca_config import BuilderHost
    monkeypatch.setattr(settings,'builder_hosts',{'builder':BuilderHost(host='builder.example.edu',user='builder',private_key_path='/run/key',known_hosts_path='/run/known',scope_id='scope-prueba',limit_bytes=10000,job_bytes=100)})
    seed=await make_trial(db,admin);draft=await db.get(DefinicionServicio,seed.definicion_id);draft.incorporacion_id=seed.incorporacion_id
    did=draft.id;inc=seed.incorporacion_id;await db.delete(seed);await db.flush()
    second=DefinicionServicio(codigo='drawio-other',version='1.0.0',producto='drawio',modelo_servicio='saas',manifest={},incorporacion_id=inc)
    db.add(second);await db.flush();second_id=second.id;aid=admin.id
    template.default_vcpus=2;await db.commit()
    pedido=await preparar_pedido(db,catedra,usuario_catedra,template)
    evaluation=await evaluacion_service.evaluar(db,pedido.id,actor=admin,payload=seleccion(template),pve=proxmox)
    pid=pedido.id;await db.commit();barrier=asyncio.Barrier(2)
    async def admit(index):
        async with pg_sessions() as session:
            actor=await session.get(Usuario,aid);await barrier.wait()
            try:
                if index==1 and competitor=='aprobacion':
                    result=await admision_service.aprobar(session,pid,actor=actor,payload=evaluation['seleccion']|{'capacidad_token':evaluation['capacidad_token']},clave='capacity-approve',pve=proxmox)
                else:
                    result=await ensayo_service.iniciar(session,did if index==0 else second_id,actor=actor,data=EnsayoCreate(incorporacion_id=inc,revision_esperada=1,perfil_ensayo_id='prueba'),clave=f'capacity-trial-{index}',pve=proxmox,builder=PipelineBuilder(drawio_manifest()))
                await session.commit();return result.status_code
            except HTTPException as exc:await session.rollback();return exc.status_code
    outcomes=await asyncio.gather(admit(0),admit(1))
    assert outcomes.count(409)==1 and sum(s in {200,202} for s in outcomes)==1
    async with pg_sessions() as session:
        ledgers=(await session.scalars(select(CompromisoCapacidad).where(CompromisoCapacidad.liberado_at.is_(None)))).all()
        assert sum(l.vcpus_retenidos for l in ledgers)==2
        assert len(ledgers) in {1,2}
        trials=(await session.scalars(select(EnsayoPreparacion))).all()
        assert len(trials)==(1 if len(ledgers)==2 else 0)


async def test_dos_workers_reclaman_una_sola_operacion(db,admin,pg_sessions):
    from tests.test_ensayo_limpieza_010 import make_trial
    from app.services import ensayo_service,ensayo_worker
    trial=await make_trial(db,admin);ensayo_service.enqueue(db,trial,kind='resolver',context={});await db.commit()
    barrier=asyncio.Barrier(2)
    async def claim():
        async with pg_sessions() as session:
            await barrier.wait();result=await ensayo_worker.claim(session,uuid4());await session.commit();return result
    results=await asyncio.gather(claim(),claim())
    assert sum(result is not None for result in results)==1
