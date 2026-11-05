"""Gateway aislado: sesión NAP, alcance actual y secretos sólo en el servidor."""
from datetime import timedelta
import hashlib
import httpx
import pytest
from sqlalchemy import select,func
from app.application_gateway import app as gateway,get_http_client
from app.config import get_settings
from app.database import get_db
from app.models.acceso_aplicacion import AccesoAplicacion
from app.models.autenticacion import SesionAutenticacion
from app.models.definicion_servicio import DefinicionServicio
from app.models.identidad_infraestructura import IdentidadInfraestructura
from app.models.pedido import Pedido,EstadoPedido
from app.models.servicio import Servicio,EstadoServicio
from app.services import aplicacion_access_service as access
from app.utils.clock import clock
from app.utils.secretos import configured_keyring
from tests.test_entrega_acceso_009 import prepared_access
from tests.test_evidencias_009 import evidence_definition,prepared_instance_document
from tests.auth_helpers import headers_para
from tests.factories import crear_usuario

PASSWORD='private-test-application-password'

@pytest.fixture
async def drawio(db,prepared_access,monkeypatch):
    service=await db.get(Servicio,prepared_access[0])
    definition=await db.get(DefinicionServicio,service.definicion_version_id)
    definition.producto='drawio';definition.modelo_servicio=service.modelo_servicio='saas'
    identity=await db.get(IdentidadInfraestructura,service.identidad_infraestructura_id)
    identity.ownership_verificada_at=clock.now()
    instance={'host':'draw.example.edu','address':'10.50.0.101'}
    settings=get_settings()
    monkeypatch.setattr(settings,'application_gateway_domain','apps.example.edu')
    monkeypatch.setattr(settings,'application_gateway_port',443)
    monkeypatch.setattr(settings,'application_gateway_ca_file','/test/ca.pem')
    monkeypatch.setattr(settings,'infrastructure_profile',{'cluster_id':identity.cluster_id})
    monkeypatch.setattr(settings,'network_profiles',{'test':{'nodes':['pve1'],'allowed_cidrs':['10.50.0.0/24'],
        'instances':{str(identity.resource_uuid):instance}}})
    service.acceso_metadata={**service.acceso_metadata,'host':instance['host'],'addresses':[instance['address']],
        'endpoint':'https://draw.example.edu','port':443,'network_profile_id':'test','metodo':'https',
        'username':'nap_'+identity.resource_uuid.hex}
    service.credenciales_encrypted=configured_keyring().encrypt({'access_password':PASSWORD},context=f'servicio:{service.id}:secretos')
    await db.commit()
    return service

@pytest.fixture
async def app_client(db):
    calls=[]
    def upstream(request):
        calls.append(request)
        return httpx.Response(200,headers={'Content-Type':'text/html','Set-Cookie':'guest=private','WWW-Authenticate':'Basic'},
            content='<html><script>/* draw.io */</script></html>')
    async def database():yield db
    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as proxy:
        async def http_client():return proxy
        gateway.dependency_overrides[get_db]=database
        gateway.dependency_overrides[get_http_client]=http_client
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway),base_url='https://app-1.apps.example.edu') as client:
            yield client,calls
    gateway.dependency_overrides.clear()

async def enter(client,auth_catedra,drawio,app_client):
    browser,calls=app_client
    result=await client.post(f'/servicios/{drawio.id}/abrir-aplicacion',headers=auth_catedra,json={})
    assert result.status_code==200,result.text
    opening=await browser.post(result.json()['destino'],data={'codigo':result.json()['codigo']},headers={'Origin':'http://test'})
    assert opening.status_code==303,opening.text
    assert '__Host-nap_app=' in opening.headers['set-cookie']
    assert all(part in opening.headers['set-cookie'] for part in ['HttpOnly','Secure','SameSite=lax','Path=/'])
    return browser,calls,result.json(),opening

async def test_open_one_use_private_proxy_delivery_and_no_password(client,db,auth_catedra,drawio,app_client,caplog):
    metadata=(await client.get(f'/servicios/{drawio.id}/acceso',headers=auth_catedra)).json()
    assert metadata['acceso_con_nap'] and metadata['puede_abrir_con_nap'] and not metadata['puede_revelar_credenciales']
    browser,calls,ticket,opening=await enter(client,auth_catedra,drawio,app_client)
    row=await db.scalar(select(AccesoAplicacion))
    assert row.codigo_sha256==hashlib.sha256(ticket['codigo'].encode()).hexdigest() and row.consumido_at
    assert ticket['codigo'] not in repr(row.__dict__)
    assert (await browser.post(ticket['destino'],data={'codigo':ticket['codigo']},headers={'Origin':'http://test'})).status_code==401
    # La respuesta 401 revoca la cookie local: restaurar sólo para comprobar el proxy.
    browser.cookies.clear();browser.cookies.set(access.COOKIE,opening.cookies[access.COOKIE],domain='app-1.apps.example.edu',path='/')
    response=await browser.get('/?offline=1',headers={'Authorization':'Bearer browser-secret','Cookie':access.COOKIE+'='+opening.cookies[access.COOKIE]+'; nap_session=browser-secret'})
    assert response.status_code==200,response.text
    assert len(calls)==1 and calls[0].url.host=='10.50.0.101'
    assert calls[0].headers['host']=='draw.example.edu' and calls[0].extensions['sni_hostname']=='draw.example.edu'
    assert calls[0].headers['authorization'].startswith('Basic ') and 'cookie' not in calls[0].headers
    assert 'browser-secret' not in str(calls[0].headers)
    assert 'set-cookie' not in response.headers and 'www-authenticate' not in response.headers
    assert PASSWORD not in response.text+caplog.text
    await db.refresh(drawio)
    assert drawio.disponibilidad_aplicacion=='utilizable' and drawio.evidencia_acceso_id is None
    assert (await db.get(Pedido,drawio.pedido_id)).estado==EstadoPedido.ACTIVO
    count=await db.scalar(select(func.count()).select_from(__import__('app.models.notificacion',fromlist=['Notificacion']).Notificacion))
    await browser.get('/')
    assert 'cookie' not in calls[-1].headers  # Ni siquiera Set-Cookie del guest se reutiliza.
    assert await db.scalar(select(func.count()).select_from(__import__('app.models.notificacion',fromlist=['Notificacion']).Notificacion))==count
    # Cerrar NAP invalida también las peticiones siguientes de la aplicación.
    session=await db.get(SesionAutenticacion,row.sesion_id);session.revoked_at=clock.now();await db.commit()
    assert (await browser.get('/js/app.js')).status_code==401 and len(calls)==2

@pytest.mark.parametrize('change',['expired','origin','host','stopped','inactive','mfa','version','foreign'])
async def test_access_fails_closed(client,db,auth_catedra,drawio,app_client,usuario_catedra,change):
    browser,calls=app_client
    result=await client.post(f'/servicios/{drawio.id}/abrir-aplicacion',headers=auth_catedra,json={})
    assert result.status_code==200,result.text
    row=await db.scalar(select(AccesoAplicacion));session=await db.get(SesionAutenticacion,row.sesion_id)
    if change=='expired':row.expira_at=clock.now()-timedelta(seconds=1)
    if change=='stopped':drawio.estado=EstadoServicio.STOPPED
    if change=='inactive':usuario_catedra.activo=False
    if change=='mfa':usuario_catedra.totp_habilitado=True;session.mfa_verified_at=None
    if change=='version':usuario_catedra.auth_version+=1
    if change=='foreign':
        from app.models.catedra import Catedra
        (await db.get(Catedra,drawio.catedra_id)).titular_id=None
    await db.commit()
    destination=result.json()['destino'].replace('app-1.','app-2.') if change=='host' else result.json()['destino']
    response=await browser.post(destination,data={'codigo':result.json()['codigo']},headers={'Origin':'https://foreign.edu' if change=='origin' else 'http://test'})
    assert response.status_code in (401,403,409),response.text
    assert not calls and 'www-authenticate' not in response.headers

async def test_foreign_catedra_denied_before_secret_and_csrf_required(client,db,drawio,auth_catedra,monkeypatch):
    other=await crear_usuario(db,'foreign-app');foreign=await headers_para(db,other)
    monkeypatch.setattr(access,'configured_keyring',lambda:(_ for _ in ()).throw(AssertionError('No recuperar secretos ajenos')))
    assert (await client.post(f'/servicios/{drawio.id}/abrir-aplicacion',headers=foreign,json={})).status_code==403
    headers={k:v for k,v in auth_catedra.items() if k!='X-CSRF-Token'}
    assert (await client.post(f'/servicios/{drawio.id}/abrir-aplicacion',headers=headers,json={})).status_code==403

async def test_cross_origin_post_and_other_app_cookie_rejected(client,auth_catedra,drawio,app_client):
    browser,calls,ticket,opening=await enter(client,auth_catedra,drawio,app_client)
    assert (await browser.post('/save',headers={'Origin':'http://test'},content=b'bad')).status_code==403
    response=await browser.get('https://app-2.apps.example.edu/',headers={'Cookie':access.COOKIE+'='+opening.cookies[access.COOKIE]})
    assert response.status_code==401 and not calls

@pytest.mark.parametrize('failure',['auth','tls','redirect','html'])
async def test_upstream_failure_never_marks_delivered(client,db,auth_catedra,drawio,app_client,failure):
    browser,calls,ticket,opening=await enter(client,auth_catedra,drawio,app_client)
    def upstream(request):
        if failure=='tls':raise httpx.ConnectError('certificate rejected')
        if failure=='redirect':return httpx.Response(302,headers={'Location':'https://evil.edu/'})
        if failure=='auth':return httpx.Response(401,headers={'WWW-Authenticate':'Basic realm="secret"'})
        return httpx.Response(200,content='not the editor')
    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as proxy:
        async def custom_client():return proxy
        gateway.dependency_overrides[get_http_client]=custom_client
        response=await browser.get('/')
    assert response.status_code==502,response.text
    assert 'www-authenticate' not in response.headers
    await db.refresh(drawio)
    assert drawio.disponibilidad_aplicacion=='no_verificada'
    assert (await db.get(Pedido,drawio.pedido_id)).estado==EstadoPedido.EN_DESPLIEGUE

@pytest.mark.parametrize('change',['foreign','inactive','mfa','version','expired','stopped','coverage'])
async def test_current_permission_rechecked_on_each_asset(client,db,auth_catedra,usuario_catedra,drawio,app_client,change):
    browser,calls,ticket,opening=await enter(client,auth_catedra,drawio,app_client)
    row=await db.scalar(select(AccesoAplicacion));session=await db.get(SesionAutenticacion,row.sesion_id)
    if change=='foreign':
        from app.models.catedra import Catedra
        (await db.get(Catedra,drawio.catedra_id)).titular_id=None
    if change=='inactive':usuario_catedra.activo=False
    if change=='mfa':usuario_catedra.totp_habilitado=True;session.mfa_verified_at=None
    if change=='version':usuario_catedra.auth_version+=1
    if change=='expired':session.expira_at=clock.now()-timedelta(seconds=1)
    if change=='stopped':drawio.estado=EstadoServicio.STOPPED
    if change=='coverage':
        from app.models.vigencia import VigenciaAutorizada
        for period in (await db.scalars(select(VigenciaAutorizada))).all():period.revocada_at=clock.now()
    await db.commit()
    response=await browser.get('/js/app.min.js')
    assert response.status_code in (401,403,409) and not calls

async def test_service_worker_cannot_cache_a_session_behind_logout(client,auth_catedra,drawio,app_client):
    browser,calls,ticket,opening=await enter(client,auth_catedra,drawio,app_client)
    assert 'pwa=0' in opening.headers['location']
    assert (await browser.get('/service-worker.js',headers={'Service-Worker':'script'})).status_code==403
    assert (await browser.get('/js/app.js',headers={'Sec-Fetch-Dest':'serviceworker'})).status_code==403
    assert not calls

def test_gateway_must_not_share_portal_host_tree(monkeypatch):
    settings=get_settings()
    monkeypatch.setattr(settings,'app_frontend_url','http://localhost:5174')
    monkeypatch.setattr(settings,'application_gateway_ca_file','/test/ca.pem')
    for domain in ['localhost','nap.localhost','apps..example.edu','apps_bad.example.edu']:
        monkeypatch.setattr(settings,'application_gateway_domain',domain)
        assert not access.configurado()
    monkeypatch.setattr(settings,'application_gateway_domain','apps.example.edu')
    assert access.configurado()
