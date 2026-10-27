"""Generic relay tests: no guest install or real Proxmox certification."""
import httpx
import pytest
from fastapi import FastAPI,Request
from fastapi.responses import Response

from app.services import application_proxy_service as proxy

INSTANCE={'address':'172.16.36.81','host':'app81.nap.test','port':8443}
OWN='https://app-18.apps.nap.test'


@pytest.fixture
async def relay():
    app=FastAPI();calls=[]
    state={'response':lambda request:httpx.Response(200,content=b'generic application')}
    def handler(request):
        calls.append(request)
        return state['response'](request)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as upstream:
        upstream.cookies.set('foreign','other-service')
        @app.api_route('/{path:path}',methods=list(proxy.METHODS))
        async def endpoint(request:Request,path:str):
            return await proxy.relay(request,path=path,instance=INSTANCE,own_origin=OWN,client=upstream,
                safety_headers=lambda:{'Cache-Control':'no-store'})
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url=OWN) as browser:
            yield browser,calls,state


async def test_native_cookies_auth_and_methods_are_preserved_without_nap_or_shared_jar(relay):
    browser,calls,state=relay
    state['response']=lambda request:httpx.Response(401,headers=[('set-cookie','native=one; Path=/; HttpOnly'),
        ('set-cookie','__Host-nap_app=stolen; Path=/; Secure'),('set-cookie','bad=x; Domain=nap.test'),
        ('www-authenticate','Basic realm="Application"')],content=b'Login')
    response=await browser.put('/native',headers={'Origin':OWN,'Cookie':'nap_session=portal; __Host-nap_app=opening; native=current',
        'Authorization':'Basic bmF0aXZlOnNlY3JldA=='},content=b'payload')
    assert response.status_code==401 and response.text=='Login'
    request=calls[0]
    assert request.method=='PUT' and request.content==b'payload'
    assert request.url.host==INSTANCE['address'] and request.url.port==8443
    assert request.headers['host']=='app81.nap.test:8443'
    assert request.extensions['sni_hostname']==INSTANCE['host']
    assert request.headers['cookie']=='native=current' and 'portal' not in str(request.headers)
    assert request.headers['authorization'].startswith('Basic ')
    assert response.headers['www-authenticate']=='Basic realm="Application"'
    assert len(response.headers.get_list('set-cookie'))==1
    assert 'Secure' in response.headers['set-cookie'] and 'HttpOnly' in response.headers['set-cookie']
    assert response.headers['cache-control']=='no-store'
    await browser.delete('/native',headers={'Origin':OWN,'Cookie':'native=own'})
    assert calls[-1].headers['cookie']=='native=own' and 'foreign' not in str(calls[-1].headers)


@pytest.mark.parametrize('origin',[None,'https://evil.example','http://app-18.apps.nap.test'])
async def test_write_requires_own_origin_and_never_contacts_upstream(relay,origin):
    browser,calls,state=relay
    response=await browser.patch('/change',headers={'Origin':origin} if origin else {},json={'x':1})
    assert response.status_code==403 and not calls


@pytest.mark.parametrize('location',['https://evil.example/x','//app82.nap.test/x',
    'http://app81.nap.test:8443/x','https://user:secret@app81.nap.test:8443/x','/_nap/entrar'])
async def test_redirects_cannot_change_destination_or_enter_gateway_route(relay,location):
    browser,calls,state=relay
    state['response']=lambda request:httpx.Response(302,headers={'location':location})
    response=await browser.get('/')
    assert response.status_code==502 and len(calls)==1


async def test_relative_redirect_is_rewritten_and_native_app_is_not_checked_for_drawio_html(relay):
    browser,calls,state=relay
    state['response']=lambda request:httpx.Response(303,headers={'location':'/login?next=%2Fhome'})
    response=await browser.get('/')
    assert response.status_code==303 and response.headers['location']==OWN+'/login?next=%2Fhome'
    state['response']=lambda request:httpx.Response(200,content=b'Not a Draw.io document')
    assert (await browser.get('/')).text=='Not a Draw.io document'


async def test_oversized_upload_is_rejected_before_upstream(relay):
    browser,calls,state=relay
    response=await browser.post('/',headers={'Origin':OWN,'Content-Length':str(proxy.MAX_REQUEST+1)},content=b'x')
    assert response.status_code==413 and not calls


def test_cookie_jar_never_retains_native_cookies_between_services():
    jar=proxy.NoCookieJar()
    client=httpx.Client(cookies=jar,transport=httpx.MockTransport(lambda request:httpx.Response(200,headers={'set-cookie':'native=secret; Path=/'})))
    with client:
        client.get('https://app81.nap.test')
        assert not list(client.cookies.jar)


async def test_chunked_upload_is_bounded_before_application_handler(relay,monkeypatch):
    browser,calls,state=relay
    monkeypatch.setattr(proxy,'MAX_REQUEST',8)
    async def chunks():
        yield b'12345';yield b'67890'
    response=await browser.post('/',headers={'Origin':OWN},content=chunks())
    assert response.status_code==413 and not calls


@pytest.mark.parametrize('allowed,origin',[(False,OWN),(True,'https://other.example')])
async def test_websocket_requires_declaration_and_own_origin(monkeypatch,allowed,origin):
    await websocket_case(monkeypatch,allowed=allowed,origin=origin,revoked=False)


async def websocket_case(monkeypatch,*,allowed=True,origin=OWN,revoked=True):
    import asyncio
    from types import SimpleNamespace
    from app.services import application_websocket_service as ws
    from fastapi import HTTPException
    calls=[];closed=[];checks=[];sent=[]
    instance={**INSTANCE,'access':{'websocket':allowed}}
    service=SimpleNamespace(id=18,configuracion_despliegue_id='fixture-configuration')
    identity=SimpleNamespace(id='fixture-identity')
    async def authenticate(db,request):
        checks.append(True)
        if revoked and len(checks)>1:raise HTTPException(403)
        return None,None,service,identity,instance
    monkeypatch.setattr(ws.access,'autenticar_aplicacion',authenticate)
    monkeypatch.setattr(ws.access,'origen',lambda sid:OWN)
    monkeypatch.setattr(ws,'RECHECK_SECONDS',.01)
    class DB:
        async def commit(self):pass
        async def rollback(self):pass
    class Socket:
        scope={'type':'websocket','scheme':'wss','server':('app-18.apps.nap.test',443),'path':'/events','query_string':b'',
            'headers':[(b'host',b'app-18.apps.nap.test'),(b'origin',origin.encode()),
                (b'cookie',b'__Host-nap_app=nap-opening; nap_session=portal-secret; native=own')]}
        async def accept(self,**kwargs):sent.append('accepted')
        async def receive(self):await asyncio.Future()
        async def send_text(self,value):sent.append(value)
        async def send_bytes(self,value):sent.append(value)
        async def close(self,*,code):closed.append(code)
    class Upstream:
        subprotocol=None
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        def __aiter__(self):return self
        async def __anext__(self):await asyncio.Future()
        async def send(self,value):sent.append(value)
    def connector(uri,**kwargs):
        calls.append((uri,kwargs));return Upstream()
    await asyncio.wait_for(ws.relay(Socket(),path='events',db=DB(),connector=connector,ssl_context='fixture-CA'),timeout=1)
    assert 1008 in closed
    if allowed and origin==OWN:
        assert sent==['accepted'] and len(checks)==2
        uri,kwargs=calls[0]
        assert uri=='wss://app81.nap.test:8443/events'
        assert kwargs['host']==INSTANCE['address'] and kwargs['server_hostname']==INSTANCE['host']
        assert kwargs['proxy'] is None and kwargs['ssl']=='fixture-CA'
        assert kwargs['additional_headers']['Cookie']=='native=own'
        assert 'portal-secret' not in str(kwargs)
    else:assert not calls and not sent


async def test_websocket_revocation_closes_live_connection_and_does_not_change_destination(monkeypatch):
    await websocket_case(monkeypatch)


def test_websocket_never_follows_redirect_even_for_same_host():
    from app.services.application_websocket_service import FixedConnect
    connection=object.__new__(FixedConnect)
    error=RuntimeError('redirect must stay rejected')
    assert connection.process_redirect(error) is error


async def test_response_limit_closes_upstream_instead_of_buffering_unlimited_output(relay,monkeypatch):
    browser,calls,state=relay
    closed=[]
    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):yield b'0123456789'
        async def aclose(self):closed.append(True)
    monkeypatch.setattr(proxy,'MAX_RESPONSE',8)
    state['response']=lambda request:httpx.Response(200,stream=Stream())
    with pytest.raises(Exception):await browser.get('/')
    assert closed


async def test_native_csp_is_preserved_in_addition_to_gateway_policy(relay):
    browser,calls,state=relay
    state['response']=lambda request:httpx.Response(200,headers={'content-security-policy':"script-src 'nonce-own'"},content=b'OK')
    response=await browser.get('/')
    assert "script-src 'nonce-own'" in response.headers.get_list('content-security-policy')
