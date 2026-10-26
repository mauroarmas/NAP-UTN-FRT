"""Descubrimiento oficial de sólo lectura, límites y cache explícita."""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import re
import time
import httpx
from app.config import get_settings
from app.utils.errors import error

API = 'https://api.github.com/repos/community-scripts/ProxmoxVE'
PATH = re.compile(r'^ct/([a-z0-9][a-z0-9_-]{0,120})\.sh$')


class CommunityScriptsClient:
    def __init__(self, *, client=None, settings=None):
        self.client = client
        self.settings = settings or get_settings()
        self.cached = None
        self.expires_at = 0
        self.lock = asyncio.Lock()

    async def _json(self, client, suffix, budget):
        headers = {'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'}
        config = self.settings.biblioteca_fuente
        if config.token: headers['Authorization'] = 'Bearer ' + config.token
        async with client.stream('GET', API + suffix, headers=headers, follow_redirects=False,
                timeout=httpx.Timeout(10,connect=3)) as response:
            response.raise_for_status()
            raw = bytearray()
            async for chunk in response.aiter_bytes():
                budget[0] += len(chunk)
                if budget[0] > config.max_bytes: raise ValueError('Indice demasiado grande')
                raw.extend(chunk)
            value = __import__('json').loads(raw)
            if not isinstance(value,dict): raise ValueError('Respuesta inválida')
            return value

    async def _load(self, client):
        budget = [0]
        ref = await self._json(client,'/git/ref/heads/main',budget)
        revision = ref['object']['sha']
        if not re.fullmatch(r'[a-f0-9]{40}',revision): raise ValueError('Revisión inválida')
        tree = await self._json(client,f'/git/trees/{revision}?recursive=1',budget)
        if tree.get('truncated') is not False or not isinstance(tree.get('tree'),list):
            raise ValueError('Indice incompleto')
        items = []
        for entry in tree['tree']:
            match = PATH.fullmatch(entry.get('path','')) if isinstance(entry,dict) else None
            if not match or entry.get('type')!='blob' or entry.get('mode') not in {'100644','100755'}:continue
            slug = match[1]
            url = f'https://raw.githubusercontent.com/community-scripts/ProxmoxVE/{revision}/ct/{slug}.sh'
            command = f'bash -c "$(curl -fsSL {url})"'
            drawio = slug=='drawio'
            items.append({'identidad_externa':entry['path'], 'nombre':'Draw.io' if drawio else slug.replace('-',' ').title(),
                'descripcion':None, 'categorias':['diagramas'] if drawio else [],
                'aliases':['drawio','draw.io','diagramas'] if drawio else [slug],
                'procedencia_datos':{'nombre':'NAP','categorias':'NAP','aliases':'NAP'},
                'comando_origen':command, 'comando_sha256':hashlib.sha256(command.encode()).hexdigest(),
                'url_origen':f'https://github.com/community-scripts/ProxmoxVE/blob/{revision}/ct/{slug}.sh',
                'revision_fuente':revision, 'version_externa':None, 'requisitos':None,
                'compatibilidad':'adaptador_disponible' if drawio else 'sin_comprobar',
                'faltantes':['version','requisitos','descripcion']})
            if len(items)>self.settings.biblioteca_fuente.max_entries:raise ValueError('Demasiadas aplicaciones')
        return sorted(items,key=lambda item:item['identidad_externa']), {'proveedor':'community-scripts','revision':revision,
            'consultada_at':datetime.now(timezone.utc).isoformat(),'cache':False,'estado':'disponible'}

    async def index(self):
        if not self.settings.biblioteca_fuente.enabled:
            raise error(502,'proveedor_no_disponible','La búsqueda externa no está habilitada',reintentable=True)
        async with self.lock:
            if self.cached is not None and time.monotonic()<self.expires_at:
                items,info=deepcopy(self.cached)
                return items,{**info,'cache':True}
            try:
                async with asyncio.timeout(self.settings.biblioteca_fuente.deadline_seconds):
                    if self.client is not None:
                        result=await self._load(self.client)
                    else:
                        async with httpx.AsyncClient(trust_env=False) as client:result=await self._load(client)
                self.cached=deepcopy(result)
                self.expires_at=time.monotonic()+self.settings.biblioteca_fuente.cache_seconds
                return result
            except (httpx.HTTPError,ValueError,KeyError,TypeError,TimeoutError):
                if self.cached is not None:
                    items,info=deepcopy(self.cached)
                    return items,{**info,'cache':True,'estado':'desactualizada'}
                raise error(502,'proveedor_no_disponible','No se pudo consultar la biblioteca externa; reintentá',reintentable=True) from None


_source = None


def get_fuente():
    global _source
    settings=get_settings()
    if _source is None or _source.settings is not settings:_source=CommunityScriptsClient(settings=settings)
    return _source
