from datetime import timedelta
from uuid import UUID, uuid4
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import get_settings
from app.models.definicion_servicio import DefinicionServicio
from app.models.ensayo_preparacion import EnsayoPreparacion
from app.models.operacion_ensayo import OperacionEnsayo
from app.models.compromiso_capacidad import CompromisoCapacidad
from app.models.recurso_template import RecursoTemplate
from app.models.evidencia import Evidencia
from app.schemas.preparacion_simple import PublicarAplicacion, PrepararAplicacion, SIMPLE_CHECKS
from app.schemas.biblioteca_config import BuilderHost
from app.services import preparacion_simple_service as simple, ensayo_service, ensayo_worker, ensayo_cleanup_service, catalogo_service
from app.utils.clock import clock
from tests.test_ensayo_limpieza_010 import make_trial
from tests.test_ensayo_worker_010 import config
from tests.test_ensayo_pipeline_010 import PipelineBuilder
from tests.test_drawio_entrega_010 import DrawRunner
from tests.drawio_helpers import drawio_manifest
from tests.capacity_helpers import perfil_capacidad  # noqa: F401


async def setup(db, admin, proxmox, monkeypatch, profile):
    config(monkeypatch); settings=get_settings()
    monkeypatch.setattr(settings,'builder_hosts',{'builder':BuilderHost(host='builder.example.edu',user='builder',private_key_path='/run/key',known_hosts_path='/run/known',scope_id='scope-prueba',limit_bytes=10000,job_bytes=5000)})
    seed=await make_trial(db,admin); definition=await db.get(DefinicionServicio,seed.definicion_id)
    definition.incorporacion_id=seed.incorporacion_id
    inc,did=seed.incorporacion_id,definition.id
    await db.delete(seed);await db.commit()
    manifest=drawio_manifest();profile['cluster_id']=manifest['validation']['cluster_uuid'];proxmox.pools['ensayos']=[]
    instances={str(uuid4()):{'host':f'preparacion-{n}.example.edu','address':f'10.50.0.{101+n}','mac_address':f'02:00:00:00:00:0{n+1}','products':['drawio']} for n in range(2)}
    monkeypatch.setattr(settings,'network_profiles',{'red-prueba':{'bridge':'vmbr0','nodes':['pve1'],'allowed_cidrs':['10.50.0.0/24'],'client_cidrs':['10.50.0.0/24'],'instances':instances}})
    monkeypatch.setattr(proxmox,'get_version',lambda:{'version':'9.2.2'},raising=False)
    return inc,did,PipelineBuilder(manifest)


async def test_sin_configuracion_informa_el_faltante_sin_crear_otra_version(client,db,admin,auth_admin,auth_catedra):
    seed=await make_trial(db,admin);did=seed.definicion_id;inc=seed.incorporacion_id
    definition=await db.get(DefinicionServicio,did);definition.incorporacion_id=inc
    await db.delete(seed);await db.commit()
    url=f'/biblioteca/incorporaciones/{inc}'
    assert (await client.get(url+'/preparacion',headers=auth_catedra)).status_code==403
    status=await client.get(url+'/preparacion',headers=auth_admin)
    assert status.status_code==200 and not status.json()['puede_preparar']
    assert 'conexión con Proxmox' in status.json()['mensaje']
    result=await client.post(url+'/preparar',json={},headers=auth_admin|{'Idempotency-Key':'no-profile'})
    assert result.status_code==409
    assert await db.scalar(select(func.count()).select_from(EnsayoPreparacion))==0
    assert await db.scalar(select(func.count()).select_from(DefinicionServicio).where(DefinicionServicio.incorporacion_id==inc))==1
    for path,body in [('preparar',{}),('confirmar-funcionamiento',{'funciona':True}),('publicar',{'nombre':'Diagramas','tamano':'small'}),('eliminar',{})]:
        assert (await client.post(url+'/'+path,json=body,headers=auth_catedra|{'Idempotency-Key':path})).status_code==403


@pytest.mark.parametrize('publish',[True,False])
async def test_alta_simple_sin_plazo_y_publicacion_o_eliminacion(db,engine,admin,proxmox,perfil_capacidad,monkeypatch,publish):
    inc,did,builder=await setup(db,admin,proxmox,monkeypatch,perfil_capacidad)
    metadata=PrepararAplicacion(nombre='Diagramas preparados',descripcion='Prácticas',tamano='medium')
    result=await simple.preparar(db,inc,actor=admin,clave='simple-start',data=metadata,pve=proxmox,builder=builder)
    assert result.status_code==202
    tid=UUID(result.resultado['preparacion_id']);await db.commit()
    trial=await db.get(EnsayoPreparacion,tid)
    assert trial.expires_at is None and trial.aviso_at is None
    replay=await simple.preparar(db,inc,actor=admin,clave='simple-start',data=metadata,pve=proxmox,builder=builder)
    assert replay.replayed
    same=await simple.preparar(db,inc,actor=admin,clave='another-click',pve=proxmox,builder=builder)
    assert same.resultado['preparacion_id']==str(tid)
    assert same.resultado['datos_servicio']==metadata.model_dump()
    await db.commit();sessions=async_sessionmaker(engine,expire_on_commit=False)
    for _ in range(20):
        for op in (await db.scalars(select(OperacionEnsayo).where(OperacionEnsayo.ensayo_id==tid))).all():op.next_poll_at=clock.now()
        await db.commit();await ensayo_worker.procesar_una(sessions,builder=builder,pve=proxmox,runner=DrawRunner())
        trial=await ensayo_service.obtener(db,tid);await db.commit()
        if trial.estado=='lista_para_comprobar':break
    assert trial.estado=='lista_para_comprobar'
    assert trial.confirmada_por==admin.id
    assert (await simple.estado(db,inc,actor=admin))['estado']=='lista_para_probar'
    future=clock.now()+timedelta(days=2)
    with monkeypatch.context() as m:
        m.setattr(clock,'now',lambda:future)
        m.setattr(ensayo_cleanup_service,'procesar',AsyncMock(return_value=False))
        await ensayo_cleanup_service.tick(db)
        await db.refresh(trial);assert not trial.cancelada_at and trial.estado=='lista_para_comprobar'
    if publish:
        monkeypatch.setattr(catalogo_service,'comprobar_disponibilidad',AsyncMock())
        confirmed=await simple.confirmar(db,inc,actor=admin,funciona=True,clave='works',pve=proxmox)
        assert confirmed.status_code==202;await db.commit()
        evidence=await db.get(Evidencia,trial.evidencia_id)
        assert evidence is not None
        import json
        assert set(json.loads(evidence.documento_canonico)['resultado']['checks'])==SIMPLE_CHECKS
        await ensayo_worker.procesar_una(sessions,builder=builder,pve=proxmox)
        state=await simple.estado(db,inc,actor=admin);assert state['estado']=='lista_para_publicar'
        approved=await simple.publicar(db,inc,actor=admin,data=PublicarAplicacion(nombre='Diagramas',tamano='small'),clave='publish')
        assert approved.resultado['estado']=='publicada';await db.commit()
        row=await db.scalar(select(RecursoTemplate).where(RecursoTemplate.nombre=='Diagramas'))
        assert row and row.activo and row.default_ram_mb==512
        repeated=await simple.publicar(db,inc,actor=admin,data=PublicarAplicacion(nombre='Diagramas',tamano='small'),clave='publish')
        assert repeated.replayed
    else:
        deleted=await simple.confirmar(db,inc,actor=admin,funciona=False,clave='does-not-work',pve=proxmox)
        assert deleted.resultado['estado']=='eliminando';await db.commit()
    for _ in range(24):
        await ensayo_cleanup_service.procesar(sessions,builder=builder,pve=proxmox)
        trial=await ensayo_service.obtener(db,tid);await db.commit()
        if trial.limpieza_estado=='confirmada':break
    assert trial.limpieza_estado=='confirmada'
    assert len(proxmox.eliminados)==2
    assert (await simple.estado(db,inc,actor=admin))['estado']==('publicada' if publish else 'eliminada')
    ledgers=(await db.scalars(select(CompromisoCapacidad).where(CompromisoCapacidad.recurso_ensayo_id.is_not(None)))).all()
    assert all(row.liberado_at for row in ledgers)


async def test_agregar_completa_sin_pasos_manuales_y_poll_stage_admite_contrato(db, engine, admin, proxmox, perfil_capacidad, monkeypatch):
    from app.schemas.build_runner import BuildRequest
    inc, did, original = await setup(db, admin, proxmox, monkeypatch, perfil_capacidad)
    class AsyncStage:
        def __init__(self): self.pending = {}; self.polled = False
        async def execute(self, request, *, host_id):
            if request['operation_id'] in self.pending and request['action'] == 'status':
                BuildRequest.model_validate(request)  # Rechazaba validated_manifest en status y quedaba clavado.
                self.polled = True
                return self.pending[request['operation_id']]
            result = await original.execute(request, host_id=host_id)
            if request['action'] == 'stage' and request.get('validated_manifest'):
                self.pending[request['operation_id']] = result
                return {'status': 'accepted', 'result': {}}
            return result
    builder = AsyncStage()
    monkeypatch.setattr(catalogo_service, 'comprobar_disponibilidad', AsyncMock())
    result = await simple.preparar(db, inc, actor=admin, clave='agregar-directo',
        data=PublicarAplicacion(nombre='Diagramas', tamano='small'), automatico=True, pve=proxmox, builder=builder)
    assert result.resultado['alta_automatica']
    tid = UUID(result.resultado['preparacion_id'])
    await db.commit()
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    for _ in range(26):
        for op in (await db.scalars(select(OperacionEnsayo).where(OperacionEnsayo.ensayo_id == tid))).all():
            op.next_poll_at = clock.now()
        await db.commit()
        await ensayo_worker.procesar_una(sessions, builder=builder, pve=proxmox, runner=DrawRunner())
        await simple.completar_altas(sessions, pve=proxmox)
        state = await simple.estado(db, inc, actor=admin)
        await db.commit()
        if state['estado'] == 'publicada': break
    assert state['estado'] == 'publicada', state
    assert builder.polled
    row = await db.scalar(select(RecursoTemplate).where(RecursoTemplate.nombre == 'Diagramas'))
    assert row and row.activo
    await simple.completar_altas(sessions, pve=proxmox)
    assert await db.scalar(select(func.count()).select_from(RecursoTemplate).where(RecursoTemplate.nombre == 'Diagramas')) == 1
