"""Bounded OCI metadata resolver. No daemon, layers, execution or free URL.

Every connection pins an authorized IP while retaining the institutional Host,
TLS SNI and CA. A challenge cannot choose a token server, scope or redirect.
"""
import asyncio
import base64
from hashlib import sha256
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import ssl
import stat
from urllib.parse import urlsplit
from urllib.request import parse_http_list,parse_keqv_list

import httpx

from app.config import get_settings
from app.schemas.oci_registry import RegistryProfile
from app.schemas.configuracion_despliegue import FORBIDDEN_TARGETS
from app.utils.errors import error

IMAGE_TYPES={'application/vnd.oci.image.manifest.v1+json','application/vnd.docker.distribution.manifest.v2+json'}
INDEX_TYPES={'application/vnd.oci.image.index.v1+json','application/vnd.docker.distribution.manifest.list.v2+json'}
CONFIG_TYPES={'application/vnd.oci.image.config.v1+json','application/vnd.docker.container.image.v1+json'}
LAYER_TYPES={'application/vnd.oci.image.layer.v1.tar','application/vnd.oci.image.layer.v1.tar+gzip',
    'application/vnd.oci.image.layer.v1.tar+zstd','application/vnd.docker.image.rootfs.diff.tar.gzip'}
DIGEST=r'sha256:[a-f0-9]{64}'
REPOSITORY=r'[a-z0-9]+(?:[._-][a-z0-9]+)*(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)*'


def invalid():return error(422,'imagen_no_admitida','Revisá la imagen y su compatibilidad con la plataforma.')
def unavailable():return error(502,'registry_no_disponible','No se pudo verificar la imagen en el registro autorizado.')


def reference(value):
    try:
        if type(value) is not str or len(value)>512 or value!=value.strip() or any(c.isspace() for c in value):raise ValueError()
        if '@' in value:
            name,tag=value.split('@')
            if not re.fullmatch(DIGEST,tag):raise ValueError()
        else:
            final=value.rsplit('/',1)[-1]
            if ':' in final:name,tag=value.rsplit(':',1)
            else:name,tag=value,'latest'
            if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}',tag):raise ValueError()
        parts=name.split('/')
        if len(parts)>1 and ('.' in parts[0] or ':' in parts[0] or parts[0]=='localhost'):host,repository=parts[0],'/'.join(parts[1:])
        else:host,repository='docker.io',name
        if host=='docker.io' and '/' not in repository:repository='library/'+repository
        parsed=urlsplit('https://'+host)
        if (not re.fullmatch(r'[a-z0-9.-]+(?::[1-9][0-9]{0,4})?',host) or not parsed.hostname
                or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?',label) for label in parsed.hostname.split('.'))
                or parsed.username or parsed.password or parsed.port and parsed.port>65535
                or not re.fullmatch(REPOSITORY,repository) or len(repository)>255):raise ValueError()
        return host,repository,tag
    except (ValueError,TypeError):raise invalid() from None


def digest(raw):return 'sha256:'+sha256(raw).hexdigest()


def document(raw):
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:raise ValueError()
            result[key]=value
        return result
    value=json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda v:(_ for _ in ()).throw(ValueError()))
    if type(value) is not dict:raise ValueError()
    return value


def descriptor(value,types,*,maximum):
    if (type(value) is not dict or value.get('mediaType') not in types
            or type(value.get('digest')) is not str or not re.fullmatch(DIGEST,value['digest'])
            or type(value.get('size')) is not int or not 0<=value['size']<=maximum or value.get('urls')):raise ValueError()
    return value


class Resolver:
    def __init__(self,profile,*,transport_factory=httpx.AsyncHTTPTransport,lookup=None,credentials=None):
        self.profile=RegistryProfile.model_validate(profile)
        self.transport_factory,self.lookup=transport_factory,lookup or self._dns
        self.credentials=credentials
        self.authorization=None

    @staticmethod
    async def _dns(host,port):
        rows=await asyncio.get_running_loop().getaddrinfo(host,port,family=socket.AF_INET,type=socket.SOCK_STREAM)
        return sorted({row[4][0] for row in rows})

    async def _get(self,endpoint,path,*,params=None,query=None,authorization=None,limit=8388608,blob_redirect=False):
        addresses=await self.lookup(endpoint.host,endpoint.port)
        if not addresses or len(addresses)>32:raise ValueError()
        for raw in addresses:
            address=ipaddress.IPv4Address(raw)
            if (str(address)!=raw or address.is_loopback or address.is_link_local or address.is_multicast or address.is_unspecified
                    or str(address)==get_settings().proxmox_host
                    or raw not in endpoint.addresses and not (endpoint.allow_public and address.is_global)):raise ValueError()
        address=sorted(addresses)[0]
        context=ssl.create_default_context(cafile=endpoint.ca_file or None)
        headers={'Host':endpoint.host+(':'+str(endpoint.port) if endpoint.port!=443 else ''),
            'Accept':', '.join(sorted(IMAGE_TYPES|INDEX_TYPES|CONFIG_TYPES)),'Accept-Encoding':'identity'}
        if authorization:headers['Authorization']=authorization
        # Low-level transport deliberately avoids AsyncClient's URL log: a CDN
        # may use a signed query. It also has no cookie jar or redirect behavior.
        async with self.transport_factory(verify=context,trust_env=False,retries=0) as transport:
            url=httpx.URL(scheme='https',host=address,port=endpoint.port,path=path,query=query)
            request=httpx.Request('GET',url,params=params,headers=headers,
                extensions={'sni_hostname':endpoint.host,'timeout':{'connect':5,'read':10,'write':5,'pool':5}})
            response=await transport.handle_async_request(request)
            try:
                accepted={200,401}|({301,302,303,307,308} if blob_redirect else set())
                if response.status_code not in accepted or response.headers.get('content-encoding','identity')!='identity':raise ValueError()
                raw=bytearray()
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    raw.extend(chunk)
                    if len(raw)>limit:raise ValueError()
                return response.status_code,response.headers,bytes(raw)
            finally:await response.aclose()

    def _basic(self):
        if self.credentials is None:return None
        values=self.credentials()
        if (type(values) is not dict or set(values)!={'username','password'} or any(type(v) is not str or not v or len(v)>4096 for v in values.values())):raise ValueError()
        if ':' in values['username']:raise ValueError()
        return 'Basic '+base64.b64encode((values['username']+':'+values['password']).encode()).decode('ascii')

    async def _registry_get(self,path,*,limit=8388608):
        if self.authorization is None and self.profile.token_endpoint is None:self.authorization=self._basic()
        blob=bool('/blobs/' in path)
        status,headers,raw=await self._get(self.profile.registry,path,authorization=self.authorization,limit=limit,blob_redirect=blob)
        if status==200:return headers,raw
        if status in {301,302,303,307,308}:return await self._blob_redirect(headers,limit=limit)
        if self.profile.token_endpoint is None:raise ValueError()
        challenge=headers.get('www-authenticate','')
        if len(challenge)>4096 or not challenge.lower().startswith('bearer '):raise ValueError()
        parts=parse_http_list(challenge[7:]);params=parse_keqv_list(parts)
        if len(parts)!=len(params) or set(params)-{'realm','service','scope'}:raise ValueError()
        endpoint=self.profile.token_endpoint
        realm='https://'+endpoint.host+(':'+str(endpoint.port) if endpoint.port!=443 else '')+self.profile.token_path
        if (params.get('realm')!=realm or params.get('service')!=self.profile.token_service
                or params.get('scope',self.scope)!=self.scope):raise ValueError()
        code,_,token_raw=await self._get(endpoint,self.profile.token_path,params={'service':self.profile.token_service,'scope':self.scope},
            authorization=self._basic(),limit=32768)
        token_doc=document(token_raw);token=token_doc.get('token') or token_doc.get('access_token')
        if code!=200 or type(token) is not str or not re.fullmatch(r'[A-Za-z0-9._~+/=-]{1,16384}',token):raise ValueError()
        self.authorization='Bearer '+token
        status,headers,raw=await self._get(self.profile.registry,path,authorization=self.authorization,limit=limit,blob_redirect=blob)
        if status in {301,302,303,307,308}:return await self._blob_redirect(headers,limit=limit)
        if status!=200:raise ValueError()
        return headers,raw

    async def _blob_redirect(self,headers,*,limit):
        raw=headers.get('location','')
        if len(raw)>16384:raise ValueError()
        target=urlsplit(raw)
        matches=[v for v in self.profile.blob_endpoints if (v.host,v.port)==(target.hostname,target.port or 443)]
        if (len(matches)!=1 or target.scheme!='https' or target.username or target.password or target.fragment
                or not target.path.startswith('/') or '\\' in target.path):raise ValueError()
        code,headers,raw=await self._get(matches[0],target.path,query=target.query.encode('ascii'),limit=limit)
        if code!=200:raise ValueError()
        return headers,raw

    async def resolve(self,value,*,architecture):
        try:
            async with asyncio.timeout(30):return await self._resolve(value,architecture=architecture)
        except (httpx.HTTPError,OSError,ValueError,TypeError,KeyError,RecursionError,TimeoutError):raise unavailable() from None
        finally:self.authorization=None

    async def _resolve(self,value,*,architecture):
        host,repo,tag=reference(value)
        if architecture not in {'amd64','arm64'} or host not in self.profile.reference_hosts or not any(repo.startswith(p) for p in self.profile.repository_prefixes):raise ValueError()
        self.scope='repository:'+repo+':pull'
        headers,raw=await self._registry_get('/v2/'+repo+'/manifests/'+tag)
        actual=digest(raw)
        if (tag.startswith('sha256:') and tag!=actual or headers.get('docker-content-digest',actual)!=actual):raise ValueError()
        manifest=document(raw);index_digest=None
        media=manifest.get('mediaType') or headers.get('content-type','').split(';')[0]
        if manifest.get('schemaVersion')!=2:raise ValueError()
        if media in INDEX_TYPES:
            index_digest=actual
            if type(manifest.get('manifests')) is not list or len(manifest['manifests'])>100:raise ValueError()
            matches=[d for d in manifest['manifests'] if type(d) is dict and type(d.get('platform')) is dict
                and d['platform'].get('os')=='linux' and d['platform'].get('architecture')==architecture
                and d['platform'].get('variant','') in ({'','v8'} if architecture=='arm64' else {''})]
            if len(matches)!=1:raise ValueError()
            chosen=descriptor(matches[0],IMAGE_TYPES,maximum=8388608)
            headers,raw=await self._registry_get('/v2/'+repo+'/manifests/'+chosen['digest'])
            actual=digest(raw)
            if actual!=chosen['digest'] or len(raw)!=chosen['size'] or headers.get('docker-content-digest',actual)!=actual:raise ValueError()
            manifest=document(raw);media=manifest.get('mediaType') or headers.get('content-type','').split(';')[0]
        if media not in IMAGE_TYPES or manifest.get('schemaVersion')!=2 or manifest.get('artifactType') or manifest.get('subject'):raise ValueError()
        config=descriptor(manifest['config'],CONFIG_TYPES,maximum=2097152)
        layers=manifest['layers']
        if type(layers) is not list or len(layers)>256:raise ValueError()
        for layer in layers:descriptor(layer,LAYER_TYPES,maximum=8*1024**3)
        _,raw=await self._registry_get('/v2/'+repo+'/blobs/'+config['digest'],limit=2097152)
        if digest(raw)!=config['digest'] or len(raw)!=config['size']:raise ValueError()
        config_doc=document(raw)
        if config_doc.get('os')!='linux' or config_doc.get('architecture')!=architecture:raise ValueError()
        rootfs=config_doc['rootfs']
        if rootfs.get('type')!='layers' or type(rootfs.get('diff_ids')) is not list or len(rootfs['diff_ids'])!=len(layers) or any(not isinstance(v,str) or not re.fullmatch(DIGEST,v) for v in rootfs['diff_ids']):raise ValueError()
        image_config=config_doc.get('config') or {}
        volumes=image_config.get('Volumes') or {}
        if type(volumes) is not dict or len(volumes)>8 or any(v!={} for v in volumes.values()):raise ValueError()
        if any(not re.fullmatch(r'/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*',p) or len(p)>255
                or any(s in {'.','..'} for s in p.split('/'))
                or any(p==f or p.startswith(f+'/') for f in FORBIDDEN_TARGETS) for p in volumes):raise ValueError()
        return {'repositorio':host+'/'+repo,'tag_original':None if tag.startswith('sha256:') else tag,
            'manifest_digest':actual,'index_digest':index_digest,'config_digest':config['digest'],
            'os':'linux','arquitectura':architecture,'volumes':sorted(volumes)}


async def resolve_image(value,*,architecture,settings=None):
    settings=settings or get_settings()
    host,repository,tag=reference(value)
    try:
        matches=[(name,RegistryProfile.model_validate(profile)) for name,profile in settings.application_registry_profiles.items()
            if host in profile.get('reference_hosts',[])]
        if len(matches)!=1:raise ValueError()
        name,profile=matches[0]
        if not re.fullmatch(r'[a-z][a-z0-9-]{0,63}',name):raise ValueError()
        credentials=None
        if profile.credential_file:
            credentials=lambda:read_credentials(profile.credential_file)
        result=await Resolver(profile.model_dump(),credentials=credentials).resolve(value,architecture=architecture)
        return {**result,'registry_profile_id':name,'registry_profile_sha256':sha256(
            json.dumps(profile.model_dump(),sort_keys=True,separators=(',',':')).encode()).hexdigest()}
    except (ValueError,TypeError,KeyError,AttributeError):raise invalid() from None


def read_credentials(path):
    path=Path(path)
    if not path.is_absolute() or path.resolve()!=path:raise ValueError()
    parent=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        for part in path.parts[1:-1]:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
            os.close(parent);parent=child
            info=os.fstat(parent)
            if info.st_uid not in {0,os.geteuid()} or info.st_mode&0o022 and not(info.st_uid==0 and info.st_mode&stat.S_ISVTX):raise ValueError()
        if os.fstat(parent).st_mode&0o077:raise ValueError()
        descriptor=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
        with os.fdopen(descriptor,'rb') as source:
            info=os.fstat(source.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid not in {0,os.geteuid()}
                    or info.st_mode&0o077 or info.st_nlink!=1 or info.st_size>16384):raise ValueError()
            return document(source.read(16385))
    finally:os.close(parent)
