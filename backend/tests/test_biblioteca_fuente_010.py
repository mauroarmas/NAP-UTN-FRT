import asyncio
import json
import httpx
import pytest
from fastapi import HTTPException
from app.config import Settings


async def test_indice_sin_ejecutar_shell_y_cache(monkeypatch):
    from app.services.community_scripts_client import CommunityScriptsClient
    calls = []
    def handler(request):
        calls.append(str(request.url))
        if '/git/ref/' in request.url.path:
            return httpx.Response(200, json={'object': {'sha': 'a'*40}})
        return httpx.Response(200, json={'truncated': False, 'tree': [
            {'path': 'ct/drawio.sh', 'type': 'blob', 'mode': '100644'},
            {'path': 'ct/escape/../mal.sh', 'type': 'blob', 'mode': '100644'},
            {'path': 'ct/enlace.sh', 'type': 'blob', 'mode': '120000'}]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = CommunityScriptsClient(client=client, settings=Settings(_env_file=None))
        first, info = await source.index()
        assert len(first) == 1 and first[0]['nombre'] == 'Draw.io'
        assert first[0]['version_externa'] is None
        assert first[0]['revision_fuente'] == 'a'*40
        assert first[0]['compatibilidad'] == 'adaptador_disponible'
        _, cached = await source.index()
        assert cached['cache'] and len(calls) == 4
        assert 'curl' in first[0]['comando_origen']


@pytest.mark.parametrize('mode', ['rate', 'truncated', 'redirect', 'oversize', 'timeout'])
async def test_fallos_explicitos_y_cache_desactualizada(mode):
    from app.services.community_scripts_client import CommunityScriptsClient
    failed = False
    async def handler(request):
        if failed:
            if mode == 'timeout': raise httpx.ReadTimeout('timeout')
            if mode == 'rate': return httpx.Response(429, headers={'Retry-After': '30'})
            if mode == 'redirect': return httpx.Response(302, headers={'Location': 'http://127.0.0.1/private'})
            if mode == 'oversize': return httpx.Response(200, content=b'x'*9000000)
            return httpx.Response(200, json={'truncated': True, 'tree': []})
        if '/git/ref/' in request.url.path: return httpx.Response(200, json={'object': {'sha': 'a'*40}})
        return httpx.Response(200, json={'truncated': False, 'tree': []})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = CommunityScriptsClient(client=client, settings=Settings(_env_file=None))
        await source.index()
        failed = True
        source.expires_at = 0
        _, info = await source.index()
        assert info['estado'] == 'desactualizada'
        cold = CommunityScriptsClient(client=client, settings=Settings(_env_file=None))
        with pytest.raises(HTTPException) as caught: await cold.index()
        assert caught.value.status_code == 502

async def test_categorias_y_fichas_publicas_sin_filtrar_token_github():
    from app.services.community_scripts_client import CommunityScriptsClient
    settings=Settings(_env_file=None)
    settings.biblioteca_fuente.token='github-test-only'
    def handler(request):
        if request.url.host=='api.github.com':
            assert request.headers['authorization']=='Bearer github-test-only'
            if '/git/ref/' in request.url.path:return httpx.Response(200,json={'object':{'sha':'a'*40}})
            return httpx.Response(200,json={'truncated':False,'tree':[
                {'path':'ct/mariadb.sh','type':'blob','mode':'100644'},
                {'path':'ct/drawio.sh','type':'blob','mode':'100644'}]})
        assert request.url.host=='db.community-scripts.org' and 'authorization' not in request.headers
        if 'script_categories' in request.url.path:
            return httpx.Response(200,json={'page':1,'totalPages':1,'items':[{'id':'db','name':'Databases'},{'id':'office','name':'Office'}]})
        return httpx.Response(200,json={'page':1,'totalPages':1,'items':[
            {'slug':'mariadb','name':'MariaDB','description':'Base de datos','categories':['db']},
            {'slug':'drawio','name':'Draw.IO','description':'Diagramas','categories':['office']}]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        rows,info=await CommunityScriptsClient(client=client,settings=settings).index()
    assert info['categorias']==['Databases','Office'] and info['metadatos_estado']=='disponible'
    maria=next(row for row in rows if row['identidad_externa']=='ct/mariadb.sh')
    assert maria['nombre']=='MariaDB' and maria['categorias']==['Databases'] and maria['descripcion']=='Base de datos'
    assert maria['compatibilidad']=='sin_comprobar'  # Los metadatos no habilitan un instalador.
    assert next(row for row in rows if row['identidad_externa']=='ct/drawio.sh')['compatibilidad']=='adaptador_disponible'
