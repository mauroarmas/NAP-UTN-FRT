"""Targeted admission checks; fake platform evidence never enables the lab node."""
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace
from uuid import uuid4

from fastapi import HTTPException
import pytest
from sqlalchemy import select,func

from app.config import get_settings
from app.models.pedido import EstadoPedido,ModeloServicio,Pedido
from app.models.compromiso_capacidad import CompromisoCapacidad
from app.models.operacion_infraestructura import OperacionInfraestructura
from app.models.secreto_despliegue import SecretoDespliegue
from app.schemas.application_profiles import canonical
from app.services import evaluacion_service,admision_service
from tests import factories
from tests.capacity_helpers import perfil_capacidad,seleccion
from tests.test_modelos_despliegue_011 import make_configuration
from tests.test_reserva_red_aplicacion_011 import red_aplicaciones_011
from infra.applications.tests.conftest import profile_entry


@pytest.fixture
async def app_order(db,admin,catedra,usuario_catedra,template,perfil_capacidad,proxmox,
                    documento_docker,profile_entry,red_aplicaciones_011,monkeypatch,request):
    settings=get_settings();entry=deepcopy(profile_entry);profile=entry['definition']
    profile.update(cluster_uuid=perfil_capacidad['cluster_id'],nodes=['pve1'],network_profile_id='app-network')
    entry['sha256']=sha256(canonical(profile)).hexdigest()
    entry.update(estado='habilitado',motivo_codigo=None,validacion={'tipo':'proxmox_real',
        'perfil_sha256':entry['sha256'],'cluster_uuid':profile['cluster_uuid'],'platform':profile['platform'],
        'comprobaciones':['aislamiento','runtime','persistencia','acceso','secretos']})
    monkeypatch.setattr(settings,'application_profiles',{'docker-ubuntu24:1':entry})
    red_aplicaciones_011['cluster_uuid']=profile['cluster_uuid']
    doc=deepcopy(documento_docker);doc['perfil']['sha256']=entry['sha256']
    if getattr(request,'param',None)=='por_pedido':doc['secretos'][0]['modo']='por_pedido'
    config=await make_configuration(db,admin,doc)
    template.definicion_version_id=None;template.configuracion_despliegue_id=config.id
    template.modelo_servicio=ModeloServicio.SAAS;template.os_template=doc['base']['volumen_lxc']
    template.default_vcpus=2;template.default_ram_mb=1024;template.default_disk_gb=8
    proxmox.contenidos_storage[('pve1','local')]=[{'volid':template.os_template,'content':'vztmpl'}]
    await db.commit()
    pedido=await factories.crear_pedido(db,catedra.id,usuario_catedra.id,template.id,
        estado=EstadoPedido.SOLICITADO,modelo_servicio=ModeloServicio.SAAS)
    body=seleccion(template)
    body['asignacion'].update(configuracion_despliegue_id=str(config.id),tamano='medium')
    return SimpleNamespace(pedido=pedido,template=template,config=config,document=doc,entry=entry,body=body)


async def approve(db,admin,app,*,immediate=False,private=None,key='approve-app'):
    evaluation=await evaluacion_service.evaluar(db,app.pedido.id,actor=admin,payload=app.body)
    payload={**app.body,'capacidad_token':evaluation['capacidad_token'],'desplegar_inmediatamente':immediate}
    if private is not None:payload['valores_privados']=private
    result=await admision_service.aprobar(db,app.pedido.id,actor=admin,payload=payload,clave=key)
    await db.commit();return result,payload


async def test_app_approval_freezes_configuration_network_and_private_references_once(db,admin,app_order,proxmox):
    app=app_order;result,payload=await approve(db,admin,app)
    saved=deepcopy(app.pedido.asignacion_snapshot)
    assert saved['configuracion_sha256']==app.config.sha256 and saved['configuracion']==app.document
    assert saved['network_profile_id']=='app-network' and len(saved['network_sha256'])==64
    assert saved['secretos'][0]['nombre']=='APP_PASSWORD' and 'valor' not in str(saved['secretos'])
    assert app.pedido.configuracion_despliegue_id==app.config.id and app.pedido.definicion_version_id is None
    replay=await admision_service.aprobar(db,app.pedido.id,actor=admin,payload=payload,clave='approve-app')
    await db.commit()
    assert replay.replayed and replay.resultado==result.resultado
    assert await db.scalar(select(func.count()).select_from(CompromisoCapacidad))==1
    assert await db.scalar(select(func.count()).select_from(SecretoDespliegue))==1
    assert not proxmox.creados


async def test_app_approval_keeps_snapshot_after_retirement_and_then_enqueues_without_creating_a_guest(db,admin,app_order):
    from app.utils.clock import clock
    app=app_order;await approve(db,admin,app)
    before=deepcopy(app.pedido.asignacion_snapshot)
    app.config.estado='retirada';app.config.retirada_at=clock.now();await db.commit()
    result=await admision_service.desplegar(db,app.pedido.id,actor=admin,clave='deploy-retired-app')
    await db.commit()
    assert result.status_code==202
    operation=await db.scalar(select(OperacionInfraestructura))
    assert operation.contexto_seguro['configuracion_sha256']==app.config.sha256
    assert operation.contexto_seguro['asignacion']['secretos']==app.pedido.asignacion_snapshot['secretos']
    assert app.pedido.asignacion_snapshot==before


async def test_a_profile_block_prevents_dispatch_of_an_already_approved_app(db,admin,app_order):
    app=app_order;await approve(db,admin,app)
    app.entry.update(estado='bloqueado',motivo_codigo='ADMIN_BLOCKED')
    with pytest.raises(HTTPException):await admision_service.desplegar(db,app.pedido.id,actor=admin,clave='blocked-app')
    await db.rollback()
    assert await db.scalar(select(func.count()).select_from(OperacionInfraestructura))==0


async def test_teacher_can_request_the_declarative_offer_without_technical_fields(client,db,auth_catedra,app_order):
    app=app_order
    response=await client.post('/pedidos/',headers=auth_catedra|{'Idempotency-Key':'teacher-app-order'},json={
        'template_id':app.template.id,'modelo_servicio':'saas','oferta_revision':app.template.revision,
        'descripcion_requerimientos':'Aplicación para las prácticas.','vigencia':app.body['vigencia']})
    assert response.status_code==201,response.text
    pedido=await db.get(Pedido,response.json()['id'])
    assert pedido.configuracion_despliegue_id==app.config.id and pedido.definicion_version_id is None
    assert pedido.seleccion_oferta_snapshot['configuracion_sha256']==app.config.sha256
    assert await db.scalar(select(func.count()).select_from(CompromisoCapacidad))==0


@pytest.mark.parametrize('failure',['profile_blocked','small','image_missing','foreign_network'])
async def test_invalid_platform_or_size_fails_before_reserving(db,admin,app_order,proxmox,failure):
    app=app_order
    if failure=='profile_blocked':app.entry.update(estado='bloqueado',motivo_codigo='ADMIN_BLOCKED')
    if failure=='small':app.body['asignacion'].update(tamano='small',vcpus=1,ram_mb=512,disk_gb=4)
    if failure=='image_missing':proxmox.contenidos_storage[('pve1','local')]=[]
    if failure=='foreign_network':get_settings().application_network_profiles['app-network']['cluster_uuid']=str(uuid4())
    with pytest.raises(HTTPException):await approve(db,admin,app)
    await db.rollback()
    assert await db.scalar(select(func.count()).select_from(CompromisoCapacidad))==0


@pytest.mark.parametrize('app_order',['por_pedido'],indirect=True)
async def test_supplied_values_are_write_only_and_bound_to_approval_idempotency(db,admin,app_order):
    from app.models.decision_idempotente import DecisionIdempotente
    app=app_order;private='private-input-must-not-be-in-snapshots'
    _,payload=await approve(db,admin,app,private={'APP_PASSWORD':private})
    decision=await db.scalar(select(DecisionIdempotente));secret=await db.scalar(select(SecretoDespliegue))
    assert private not in repr(app.pedido.asignacion_snapshot)+repr(app.pedido.decision_snapshot)+repr(decision.resultado_referencia)+secret.valor_cifrado
    payload['valores_privados']={'APP_PASSWORD':'different-private-input'}
    with pytest.raises(HTTPException):await admision_service.aprobar(db,app.pedido.id,actor=admin,payload=payload,clave='approve-app')


async def test_node_profile_preflight_blocks_evaluation_when_node_reports_platform_changed(db,admin,app_order):
    app=app_order
    class FakeNodeRunner:
        async def execute(self, request, *, node=None, expected_fingerprint=None):
            return {
                'protocol': 'nap-application-job/1',
                'action': 'profiles',
                'ok': True,
                'data': {
                    'profiles': [{
                        'id': 'docker-ubuntu24',
                        'revision': 1,
                        'sha256': app.entry['sha256'],
                        'estado': 'bloqueado',
                        'motivo_codigo': 'PLATFORM_CHANGED',
                    }]
                },
            }
    with pytest.raises(HTTPException) as exc_info:
        await evaluacion_service.evaluar(db, app.pedido.id, actor=admin, payload=app.body, runner=FakeNodeRunner())
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail['codigo'] == 'perfil_aplicacion_no_disponible'
    assert 'cambió su versión de sistema' in exc_info.value.detail['mensaje']
    assert await db.scalar(select(func.count()).select_from(CompromisoCapacidad)) == 0

