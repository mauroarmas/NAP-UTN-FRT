from datetime import timedelta
from uuid import uuid4,UUID
from copy import deepcopy
from unittest.mock import AsyncMock
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from app.config import get_settings
from app.models.servicio import Servicio
from app.models.pedido import Pedido
from app.models.operacion_infraestructura import OperacionInfraestructura
from app.utils.clock import clock
from app.utils.secretos import configured_keyring
from tests.test_biblioteca_pedidos_010 import oferta
from tests.test_perfiles_definiciones_009 import dates
from tests.capacity_helpers import perfil_capacidad
from tests import factories


class DrawRunner:
    def __init__(self):self.requests=[]
    async def execute(self,request):
        from app.schemas.guest_runner import parse_request,canonical
        parse_request(canonical(request).encode())
        self.requests.append(deepcopy(request))
        profile=get_settings().network_profiles[request['network_profile_id']]
        instance=profile['instances'][request['resource_uuid']]
        return {**{k:request[k] for k in ['protocol','operation_id','action','resource_uuid']},
            'status':'succeeded','phase':'verified','identity_verified':True,'observed_at':clock.now().isoformat(),
            'result':{'ready':True,'bootstrap_completed':True,'host':instance['host'],'address':instance['address'],
                'addresses':[instance['address']],'port':443,'endpoint':'https://'+instance['host'],
                'username':'nap_'+UUID(request['resource_uuid']).hex,'checks':['drawio-status-v1']}}


async def test_dos_instancias_independientes_sin_fuente_y_sin_autoentrega(client,db,engine,admin,auth_admin,auth_catedra,catedra,usuario_catedra,perfil_capacidad,proxmox,monkeypatch):
    from app.services import catalogo_service,biblioteca_service
    from app.worker import procesar_una
    _,definition,template=await oferta(db,admin)
    profile=get_settings()
    perfil_capacidad['cluster_id']=definition.manifest['validation']['cluster_uuid']
    proxmox.contenidos_storage[('pve1','local')]=[{'volid':definition.manifest['image']['volume_id'],'content':'vztmpl'}]
    instances={str(uuid4()):{'host':f'diagramas-{n}.example.edu','address':f'10.50.0.{101+n}',
        'mac_address':f'02:00:00:00:00:0{n+1}','products':['drawio']} for n in range(2)}
    monkeypatch.setattr(profile,'network_profiles',{'test-network':{'bridge':'vmbr0','nodes':['pve1'],
        'allowed_cidrs':['10.50.0.0/24'],'client_cidrs':['10.50.0.0/24'],'instances':instances}})
    monkeypatch.setattr(profile,'service_artifacts',{'drawio-trial:1.0.0':{'nodes':['pve1'],'network_profile_id':'test-network'}})
    monkeypatch.setattr(catalogo_service,'comprobar_disponibilidad',AsyncMock())
    def no_source():raise AssertionError('Un despliegue no debe consultar Community Scripts')
    monkeypatch.setattr(biblioteca_service,'get_fuente',no_source)
    other_user=await factories.crear_usuario(db,'otra-catedra-drawio')
    other=await factories.crear_catedra(db,nombre='Otra Drawio',titular_id=other_user.id);await db.commit()
    other_id=other.id;cat_id=catedra.id;tid=template.id;did=definition.id
    sessions=async_sessionmaker(engine,expire_on_commit=False);runner=DrawRunner();services=[]
    for i,category in enumerate([cat_id,other_id]):
        created=await client.post('/pedidos/',json={'template_id':tid,'catedra_id':category,'modelo_servicio':'saas','vigencia':dates()},headers=auth_admin|{'Idempotency-Key':f'drawio-request-{i}'})
        assert created.status_code==201,created.text
        pid=created.json()['id']
        selection={'asignacion':{'template_id':tid,'definicion_version_id':str(did),'vcpus':1,'ram_mb':512,'disk_gb':4},'vigencia':dates()}
        evaluation=await client.post(f'/pedidos/{pid}/evaluacion',json=selection,headers=auth_admin)
        assert evaluation.status_code==200,evaluation.text
        approval=await client.post(f'/pedidos/{pid}/aprobar',json=selection|{'capacidad_token':evaluation.json()['capacidad_token']},headers=auth_admin|{'Idempotency-Key':f'drawio-approve-{i}'})
        assert approval.status_code==200,approval.text
        deployment=await client.post(f'/servicios/desplegar/{pid}',json={},headers=auth_admin|{'Idempotency-Key':f'drawio-deploy-{i}'})
        assert deployment.status_code==202,deployment.text
        await db.commit();await procesar_una(sessions,pve=proxmox,runner=runner)
        db.expire_all();op=await db.get(OperacionInfraestructura,UUID(deployment.json()['operation_id']))
        assert op.estado=='confirmada',(op.error_codigo,op.error_detalle_seguro)
        service=await db.get(Servicio,op.servicio_id);services.append(service.id)
        assert service.disponibilidad_aplicacion=='no_verificada'
        assert (await db.get(Pedido,pid)).estado.value=='en_despliegue'
    assert len(proxmox.creados)==2 and len(runner.requests)==2
    assert runner.requests[0]['resource_uuid']!=runner.requests[1]['resource_uuid']
    assert runner.requests[0]['secrets']['access_password']!=runner.requests[1]['secrets']['access_password']
    from app.services.service_access_service import metadatos,revelar
    await db.refresh(admin);await db.refresh(usuario_catedra)
    first=await metadatos(db,actor=admin,servicio_id=services[0]);assert first['metodo']=='https'
    initial=await revelar(db,actor=admin,servicio_id=services[0]);assert initial['credenciales']['password']
    from fastapi import HTTPException
    import pytest
    with pytest.raises(HTTPException) as denied:await metadatos(db,actor=usuario_catedra,servicio_id=services[1])
    assert denied.value.status_code==403
