"""End-to-end worker delivery with fake PVE/probe, never real deployment proof."""
from hashlib import sha256
from uuid import uuid4

from fastapi import HTTPException
import pytest
from sqlalchemy import select,func
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import get_settings
from app.models.servicio import Servicio
from app.models.pedido import Pedido,EstadoPedido
from app.models.operacion_infraestructura import OperacionInfraestructura
from app.models.identidad_infraestructura import IdentidadInfraestructura
from app.models.compromiso_capacidad import CompromisoCapacidad
from app.models.notificacion import Notificacion
from app.models.reserva_red_aplicacion import ReservaRedAplicacion
from app.services import aplicacion_access_service as access
from app.services.application_target_service import destination
from app.services.application_verification_service import AccessObservation
from app.utils.clock import clock
from app.worker import procesar_una,procesar_ingesta_una
from tests.test_ingesta_worker_011 import ConsoleNode
from tests.test_creacion_aplicaciones_011 import stopped_create,wake
from tests.test_admision_aplicaciones_011 import app_order,approve,perfil_capacidad,red_aplicaciones_011,profile_entry


class DeliveredNode(ConsoleNode):
    state='confirmado'
    missing_check=False
    async def execute(self,request,**kwargs):
        reply=await super().execute(request,**kwargs)
        if request['action'] in {'read','ack'}:
            reply['data'].update(fase='comprobacion',resultado={'recurso_configurado':True,
                'comprobaciones':['runtime','salud','acceso_web']+([] if self.missing_check else ['aislamiento'])})
        return reply


@pytest.fixture
async def installation(db,engine,admin,app_order,proxmox):
    sessions=async_sessionmaker(engine,expire_on_commit=False)
    await approve(db,admin,app_order,immediate=True);stopped_create(proxmox)
    node=DeliveredNode(app_order,sessions)
    await procesar_una(sessions,pve=proxmox,runner=node)
    db.expire_all()
    identity=await db.scalar(select(IdentidadInfraestructura))
    proxmox.estados[identity.vmid]='running'
    await wake(db)
    return sessions,node


@pytest.mark.parametrize('outcome',['success','bad-target','missing-check','stopped'])
async def test_only_final_job_and_matching_tls_probe_deliver_once(db,admin,usuario_catedra,installation,proxmox,outcome,monkeypatch):
    sessions,node=installation
    if outcome=='missing-check':node.missing_check=True
    if outcome=='stopped':
        identity=await db.scalar(select(IdentidadInfraestructura));proxmox.estados[identity.vmid]='stopped'
    calls=[]
    async def probe(instance):
        # An independent SQL session can read while the network check is pending.
        async with sessions() as reader:assert await reader.scalar(select(func.count()).select_from(Servicio))==1
        calls.append(instance)
        return AccessObservation(instance['host'],'172.16.36.99' if outcome=='bad-target' else instance['address'],
            instance['port'],instance['configuration_sha256'],200)
    await procesar_ingesta_una(sessions,runner=node,pve=proxmox,probe=probe)
    db.expire_all();service=await db.scalar(select(Servicio));pedido=await db.get(Pedido,service.pedido_id)
    operation=await db.scalar(select(OperacionInfraestructura));ledger=await db.scalar(select(CompromisoCapacidad))
    if outcome=='success':
        assert operation.estado=='confirmada' and pedido.estado==EstadoPedido.ACTIVO
        assert service.disponibilidad_aplicacion=='utilizable' and service.credenciales_encrypted is None
        assert service.acceso_metadata['automatic_access_verified'] is True
        assert ledger.estado=='materializado' and ledger.expira_at is None
        identity,target=await destination(db,service)
        assert target['address']==calls[0]['address']
        settings=get_settings()
        monkeypatch.setattr(settings,'application_gateway_domain','apps.example.edu')
        monkeypatch.setattr(settings,'application_gateway_ca_file','/test/ca.crt')
        await db.refresh(usuario_catedra)
        assert (await access.autorizar(db,usuario_catedra,service.id))[2]['port']==8443
        from app.services.service_access_service import metadatos
        metadata=await metadatos(db,actor=usuario_catedra,servicio_id=service.id)
        assert metadata['puede_abrir_con_nap'] and metadata['estado_entrega']=='entregado',metadata
        assert 'BookStack' not in metadata['instrucciones'] and 'verificacion_instancia' not in metadata
        notifications=await db.scalar(select(func.count()).select_from(Notificacion))
        assert await procesar_ingesta_una(sessions,runner=node,pve=proxmox,probe=probe) is False
        assert await db.scalar(select(func.count()).select_from(Notificacion))==notifications
    else:
        assert operation.estado!='confirmada' and pedido.estado==EstadoPedido.EN_DESPLIEGUE
        assert service.disponibilidad_aplicacion!='utilizable' and ledger.liberado_at is None
        if outcome in {'stopped','missing-check'}:assert not calls
    assert len(node.starts)==1


@pytest.mark.parametrize('mutation',['endpoint','released','slot','nonce','profile'])
async def test_access_destination_cannot_adopt_changed_or_released_identity(db,installation,proxmox,mutation,monkeypatch):
    sessions,node=installation
    async def probe(instance):return AccessObservation(instance['host'],instance['address'],instance['port'],instance['configuration_sha256'],200)
    await procesar_ingesta_una(sessions,runner=node,pve=proxmox,probe=probe)
    db.expire_all();service=await db.scalar(select(Servicio));allocation=await db.scalar(select(ReservaRedAplicacion))
    if mutation=='endpoint':service.acceso_metadata={**service.acceso_metadata,'endpoint':'https://evil.example'}
    if mutation=='released':allocation.liberada_at=clock.now()
    if mutation=='slot':allocation.address='172.16.36.99'
    if mutation=='nonce':service.acceso_metadata={**service.acceso_metadata,'nonce_sha256':'0'*64}
    if mutation=='profile':
        entries=get_settings().application_profiles
        entry=next(iter(entries.values()));entry.update(estado='bloqueado',motivo_codigo='ADMIN_BLOCKED')
    await db.flush()
    with pytest.raises(HTTPException):await destination(db,service)


@pytest.mark.parametrize('failure',['none','redirect','large','timeout'])
async def test_web_probe_pins_tls_destination_has_total_timeout_and_never_follows_redirect(monkeypatch,failure):
    import asyncio
    import httpx
    import ssl
    from app.services import application_verification_service as verification
    from app.services.infraestructura_io import InfraNoVerificable
    context=ssl.create_default_context()
    seen=[];closed=[]
    client_class=httpx.AsyncClient
    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            if failure=='timeout':await asyncio.sleep(.1)
            yield b'x'*(65537 if failure=='large' else 4)
        async def aclose(self):closed.append(True)
    def handler(request):
        seen.append(request)
        return httpx.Response(302 if failure=='redirect' else 200,headers={'location':'https://evil.example/'},stream=Stream())
    def client(**kwargs):
        assert kwargs['verify'] is context and kwargs['trust_env'] is False and kwargs['follow_redirects'] is False
        return client_class(**kwargs,transport=httpx.MockTransport(handler))
    monkeypatch.setattr(verification.httpx,'AsyncClient',client)
    monkeypatch.setattr(verification.ssl,'create_default_context',lambda **kwargs:context)
    instance={'host':'app81.nap.test','address':'172.16.36.81','port':8443,'configuration_sha256':'a'*64,
        'access':{'tipo':'web','probe':{'timeout_segundos':.02,'path':'/health','estados':[200]}}}
    if failure=='none':assert (await verification.probe_web(instance)).status==200
    else:
        with pytest.raises(InfraNoVerificable):await verification.probe_web(instance)
    assert len(seen)==1 and closed
    assert seen[0].url.host==instance['address'] and seen[0].extensions['sni_hostname']==instance['host']
    assert 'cookie' not in seen[0].headers and 'authorization' not in seen[0].headers


async def test_teacher_opens_generic_application_with_one_use_nap_session_and_revocation(client,db,auth_catedra,
        installation,proxmox,monkeypatch):
    import httpx
    from app.application_gateway import app as gateway,get_http_client
    from app.database import get_db
    from app.models.autenticacion import SesionAutenticacion
    from app.models.acceso_aplicacion import AccesoAplicacion
    sessions,node=installation
    async def probe(instance):return AccessObservation(instance['host'],instance['address'],instance['port'],instance['configuration_sha256'],200)
    await procesar_ingesta_una(sessions,runner=node,pve=proxmox,probe=probe)
    db.expire_all();service=await db.scalar(select(Servicio))
    settings=get_settings()
    monkeypatch.setattr(settings,'application_gateway_domain','apps.example.edu')
    monkeypatch.setattr(settings,'application_gateway_ca_file','/test/ca.crt')
    calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(200,headers={'set-cookie':'native=own; Path=/; HttpOnly'},content=b'Own application home')
    async def database():yield db
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as upstream:
        async def http_client():return upstream
        gateway.dependency_overrides[get_db]=database;gateway.dependency_overrides[get_http_client]=http_client
        try:
            opening=await client.post(f'/servicios/{service.id}/abrir-aplicacion',headers=auth_catedra,json={})
            assert opening.status_code==200,opening.text
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway),base_url=access.origen(service.id)) as browser:
                response=await browser.post('/_nap/entrar',data={'codigo':opening.json()['codigo']},headers={'Origin':'http://test'})
                assert response.status_code==303 and response.headers['location']=='/'
                response=await browser.get('/')
                assert response.status_code==200 and response.text=='Own application home'
                assert 'set-cookie' in response.headers and 'authorization' not in calls[-1].headers
                assert 'cookie' not in calls[-1].headers
                row=await db.scalar(select(AccesoAplicacion))
                session=await db.get(SesionAutenticacion,row.sesion_id);session.revoked_at=clock.now();await db.commit()
                assert (await browser.get('/')).status_code==401 and len(calls)==1
        finally:gateway.dependency_overrides.clear()
