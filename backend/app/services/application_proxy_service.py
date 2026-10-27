"""Generic HTTPS relay, isolated from Draw.io's legacy editor adapter."""
from http.cookiejar import CookieJar
from http.cookies import SimpleCookie, CookieError
from urllib.parse import urljoin, urlsplit

import httpx
from starlette.responses import StreamingResponse

from app.utils.errors import error

MAX_REQUEST=20*1024**2
MAX_RESPONSE=32*1024**2
SAFE_METHODS={'GET','HEAD','OPTIONS'}
METHODS=SAFE_METHODS|{'POST','PUT','PATCH','DELETE'}
REQUEST_HEADERS={'accept','accept-language','content-type','range','if-none-match','if-modified-since',
    'if-match','if-unmodified-since','authorization','x-requested-with','x-csrf-token','x-xsrf-token'}
RESPONSE_HEADERS={'content-type','content-disposition','etag','last-modified','accept-ranges','content-range',
    'www-authenticate','allow','retry-after','vary'}


class NoCookieJar(CookieJar):
    def set_cookie(self,*args,**kwargs): pass
    def extract_cookies(self,*args,**kwargs): pass


def reserved_cookie(name):
    return name.lower().startswith(('nap_','__host-nap','__secure-nap'))


def native_cookies(raw):
    if not raw:return ''
    if len(raw)>16384:raise error(431,'cookies_demasiado_grandes','La solicitud supera el tamaño permitido.')
    try:
        parsed=SimpleCookie();parsed.load(raw)
        return '; '.join(m.OutputString(attrs=[]) for name,m in parsed.items() if not reserved_cookie(name))
    except CookieError:raise error(400,'cookies_invalidas','La solicitud no es válida.') from None


def response_cookie(raw,instance):
    if len(raw)>8192:return None
    try:
        parsed=SimpleCookie();parsed.load(raw)
        if len(parsed)!=1:return None
        name,m=next(iter(parsed.items()))
        if reserved_cookie(name) or (m['domain'] and m['domain'].lstrip('.').lower()!=instance['host']):return None
        m['domain']='';m['secure']=True
        return m.OutputString()
    except CookieError:return None


def redirect(location,*,instance,own_origin,path):
    try:
        target=urlsplit(urljoin('https://'+instance['host']+':'+str(instance['port'])+'/'+path,location))
        own=urlsplit(own_origin)
        if (target.scheme!='https' or target.username or target.password
                or (target.hostname,target.port or 443) not in {
                    (instance['host'],instance['port']),(own.hostname,own.port or 443)}
                or target.path.startswith('/_nap/')):raise ValueError()
        return own_origin+(target.path or '/')+('?' + target.query if target.query else '')+('#'+target.fragment if target.fragment else '')
    except ValueError:raise error(502,'redireccion_no_permitida','La aplicación devolvió un destino no permitido.') from None


def upstream_headers(request,instance):
    headers={key:value for key,value in request.headers.items() if key.lower() in REQUEST_HEADERS}
    host=instance['host']+(':'+str(instance['port']) if instance['port']!=443 else '')
    headers.update({'Host':host,'Accept-Encoding':'identity'})
    cookies=native_cookies(request.headers.get('cookie',''))
    if cookies:headers['Cookie']=cookies
    if request.headers.get('origin'):headers['Origin']='https://'+host
    return headers


async def relay(request,*,path,instance,own_origin,client,safety_headers):
    if request.method not in METHODS:raise error(405,'metodo_no_permitido','Método no permitido.')
    if request.method not in SAFE_METHODS and request.headers.get('origin')!=own_origin:
        raise error(403,'origen_no_permitido','Solicitud de aplicación no permitida.')
    try:
        length=request.headers.get('content-length')
        if length is not None and (not length.isdecimal() or int(length)>MAX_REQUEST):
            raise error(413,'contenido_demasiado_grande','El archivo supera el tamaño permitido.')
    except ValueError:raise error(413,'contenido_demasiado_grande','El archivo supera el tamaño permitido.') from None
    async def body():
        size=0
        async for chunk in request.stream():
            size+=len(chunk)
            if size>MAX_REQUEST:raise error(413,'contenido_demasiado_grande','El archivo supera el tamaño permitido.')
            yield chunk
    headers=upstream_headers(request,instance)
    url=httpx.URL(scheme='https',host=instance['address'],port=instance['port'],path='/'+path,query=request.url.query.encode())
    outgoing=client.build_request(request.method,url,content=body(),headers=headers,extensions={'sni_hostname':instance['host']})
    # An injected client or a future client configuration must not add cookies.
    outgoing.headers.pop('cookie',None)
    if headers.get('Cookie'):outgoing.headers['Cookie']=headers['Cookie']
    try:upstream=await client.send(outgoing,stream=True,follow_redirects=False,auth=None)
    except httpx.HTTPError:raise error(502,'aplicacion_inaccesible','No se pudo conectar con la aplicación.') from None
    try:
        if upstream.status_code==101 or len(upstream.headers.get_list('set-cookie'))>50:
            raise error(502,'respuesta_no_permitida','La aplicación devolvió una respuesta no permitida.')
        response_headers={key:value for key,value in upstream.headers.items() if key.lower() in RESPONSE_HEADERS}
        if upstream.headers.get('location'):
            response_headers['Location']=redirect(upstream.headers['location'],instance=instance,own_origin=own_origin,path=path)
        response_headers.update(safety_headers())
        async def content():
            size=0
            try:
                async for chunk in upstream.aiter_bytes(chunk_size=65536):
                    size+=len(chunk)
                    if size>MAX_RESPONSE:raise RuntimeError('APPLICATION_RESPONSE_LIMIT')
                    yield chunk
            finally:await upstream.aclose()
        response=StreamingResponse(content(),status_code=upstream.status_code,headers=response_headers)
        for policy in upstream.headers.get_list('content-security-policy'):
            response.headers.append('content-security-policy',policy)
        for raw in upstream.headers.get_list('set-cookie'):
            cookie=response_cookie(raw,instance)
            if cookie:response.headers.append('set-cookie',cookie)
        return response
    except BaseException:
        await upstream.aclose();raise
