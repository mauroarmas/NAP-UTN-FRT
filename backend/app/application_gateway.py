"""Gateway HTTPS de aplicaciones. Se ejecuta aparte del origen del portal/API."""
from contextlib import asynccontextmanager
from html import escape
import ssl
from urllib.parse import parse_qs, urlsplit, urljoin

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from starlette.middleware.gzip import GZipMiddleware

from app.config import get_settings
from app.database import get_db
from app.services import aplicacion_access_service as access
from app.services import application_proxy_service as generic
from app.utils.clock import clock, db_utc
from app.utils.errors import error

MAX_REQUEST = 20 * 1024**2
MAX_RESPONSE = 32 * 1024**2


@asynccontextmanager
async def lifespan(app):
    settings = get_settings()
    context = ssl.create_default_context(cafile=settings.application_gateway_ca_file)
    app.state.application_ssl_context = context
    async with httpx.AsyncClient(verify=context, trust_env=False, follow_redirects=False, cookies=generic.NoCookieJar(),
        timeout=httpx.Timeout(30, connect=5, pool=5), limits=httpx.Limits(max_connections=24,max_keepalive_connections=12)) as client:
        app.state.http_client = client
        yield


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(GZipMiddleware, minimum_size=1024)


async def limited_body(request, limit):
    value=bytearray()
    async for chunk in request.stream():
        value.extend(chunk)
        if len(value)>limit: raise error(413,'contenido_demasiado_grande','El archivo supera el tamaño permitido.')
    return bytes(value)


def safety_headers():
    return {'Cache-Control':'no-store','Referrer-Policy':'no-referrer','X-Content-Type-Options':'nosniff',
        'Content-Security-Policy':"frame-ancestors 'none'; object-src 'none'; base-uri 'self'"}


@app.exception_handler(HTTPException)
async def access_error(request,exc):
    detail=exc.detail
    message=detail.get('mensaje','No se pudo abrir la aplicación.') if isinstance(detail,dict) else 'No se pudo abrir la aplicación.'
    response=HTMLResponse('<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Acceso NAP</title>'
        '<body style="font:18px system-ui;max-width:600px;margin:12vh auto;padding:24px"><h1>Acceso a la aplicación</h1><p>'+escape(message)+'</p><p><a href="'+escape(get_settings().app_frontend_url,quote=True)+'">Volver a NAP</a></p></body></html>',
        status_code=exc.status_code,headers=safety_headers())
    if exc.status_code in (401,403):response.delete_cookie(access.COOKIE,path='/',secure=True,httponly=True,samesite='lax')
    return response


@app.post('/_nap/entrar')
async def entrar(request:Request,db=Depends(get_db)):
    if request.url.query or request.headers.get('content-type','').split(';')[0]!='application/x-www-form-urlencoded':
        raise error(400,'apertura_invalida','Abrí la aplicación desde NAP.')
    try:
        fields=parse_qs((await limited_body(request,1024)).decode('ascii'),strict_parsing=True,max_num_fields=1)
        if set(fields)!={'codigo'} or len(fields['codigo'])!=1:raise ValueError()
    except (ValueError,UnicodeError):raise error(400,'apertura_invalida','Abrí la aplicación desde NAP.') from None
    cookie,session=await access.consumir_codigo(db,request,fields['codigo'][0])
    from app.models.servicio import Servicio
    service=await db.get(Servicio,access.servicio_del_host(request))
    await db.commit()
    response=RedirectResponse('/' if service.configuracion_despliegue_id else '/?offline=1&local=1&pwa=0&lang=es',status_code=303,headers=safety_headers())
    response.set_cookie(access.COOKIE,cookie,secure=True,httponly=True,samesite='lax',path='/',
        max_age=max(0,int((db_utc(session.expira_at)-clock.now()).total_seconds())))
    return response


async def get_http_client(request:Request):
    return request.app.state.http_client


async def get_websocket_connector():
    from app.services.application_websocket_service import FixedConnect
    return FixedConnect


@app.websocket('/{path:path}')
async def application_websocket(websocket:WebSocket,path:str,db=Depends(get_db),connector=Depends(get_websocket_connector)):
    from app.services.application_websocket_service import relay
    await relay(websocket,path=path,db=db,connector=connector,ssl_context=websocket.app.state.application_ssl_context)


@app.api_route('/{path:path}',methods=['GET','HEAD','POST','PUT','PATCH','DELETE','OPTIONS'])
async def application(request:Request,path:str,db=Depends(get_db),client=Depends(get_http_client)):
    # Un service worker podría responder desde caché después del cierre de NAP.
    # Los workers de cálculo normales del editor siguen disponibles.
    if request.headers.get('service-worker') or request.headers.get('sec-fetch-dest') == 'serviceworker':
        raise error(403,'modo_sin_conexion_no_disponible','Abrí la aplicación desde NAP con una sesión activa.')
    if path.startswith('_nap/'):
        raise error(404,'ruta_no_disponible','Ruta no disponible.')
    actor,session,service,identity,instance=await access.autenticar_aplicacion(db,request)
    own_origin=access.origen(service.id)
    if service.configuracion_despliegue_id:
        await db.commit()
        return await generic.relay(request,path=path,instance=instance,own_origin=own_origin,
            client=client,safety_headers=safety_headers)
    if request.method not in {'GET','HEAD','POST'}:
        raise error(405,'metodo_no_permitido','Método no permitido.')
    if request.method=='POST' and request.headers.get('origin')!=own_origin:
        raise error(403,'origen_no_permitido','Solicitud de aplicación no permitida.')
    username,password=access.credenciales(service)
    body=await limited_body(request,MAX_REQUEST)
    # El Host/SNI se conserva para validar el certificado, pero la conexión usa
    # la IP del perfil autorizado: nunca resuelve un destino recibido del navegador.
    url=httpx.URL(scheme='https',host=instance['address'],port=443,path='/'+path,query=request.url.query.encode())
    headers={key:value for key,value in request.headers.items() if key.lower() in
        {'accept','accept-language','content-type','range','if-none-match','if-modified-since'}}
    headers.update({'Host':instance['host'],'Accept-Encoding':'identity'})
    if request.headers.get('origin'):headers['Origin']='https://'+instance['host']
    await db.commit()  # No retener la transacción durante la conexión al servicio.
    try:
        outgoing=client.build_request(request.method,url,headers=headers,content=body,
            extensions={'sni_hostname':instance['host']})
        # Tampoco reutilizar cookies que el cliente HTTP haya recibido del guest.
        outgoing.headers.pop('cookie',None)
        upstream=await client.send(outgoing,auth=httpx.BasicAuth(username,password),stream=True)
        try:
            result=bytearray()
            async for chunk in upstream.aiter_bytes():
                result.extend(chunk)
                if len(result)>MAX_RESPONSE:raise error(502,'respuesta_demasiado_grande','La aplicación devolvió una respuesta demasiado grande.')
            status=upstream.status_code
            response_headers={key:value for key,value in upstream.headers.items() if key.lower() in
                {'content-type','content-disposition','etag','last-modified','accept-ranges','content-range'}}
            location=upstream.headers.get('location')
        finally:
            await upstream.aclose()
    except httpx.HTTPError:
        raise error(502,'aplicacion_inaccesible','No se pudo conectar con la aplicación. Volvé a intentarlo desde NAP.') from None
    finally: del password
    if status in (401,403) or status>=500:
        raise error(502,'aplicacion_inaccesible','La aplicación no respondió correctamente. Avisá a administración.')
    if location:
        destination=urlsplit(urljoin('https://'+instance['host']+'/'+path,location))
        if destination.netloc and (destination.scheme!='https' or destination.hostname!=instance['host'] or destination.port not in (None,443)):
            raise error(502,'redireccion_no_permitida','La aplicación devolvió un destino no permitido.')
        if destination.scheme and destination.scheme!='https':raise error(502,'redireccion_no_permitida','Destino no permitido.')
        response_headers['Location']=own_origin+(destination.path or '/')+('?' + destination.query if destination.query else '')
    if request.method=='GET' and not path and status==200:
        html=bytes(result).lower()
        if not (b'<script' in html and (b'draw.io' in html or b'diagrams.net' in html)):
            raise error(502,'aplicacion_no_confirmada','No se pudo comprobar el editor. Avisá a administración.')
        await access.confirmar_apertura(db,request)
    response_headers.update(safety_headers())
    return Response(bytes(result),status_code=status,headers=response_headers)
