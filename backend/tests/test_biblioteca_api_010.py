from uuid import uuid4
import pytest
from sqlalchemy import select, func
from tests.fakes_biblioteca import FakeFuente, DRAWIO


@pytest.fixture
def fuente(monkeypatch):
    from app.services import biblioteca_service
    source = FakeFuente()
    monkeypatch.setattr(biblioteca_service, 'get_fuente', lambda: source)
    return source


async def test_solo_admin_y_filtro_categoria(client, auth_admin, auth_catedra, fuente):
    assert (await client.get('/biblioteca/aplicaciones?q=drawio')).status_code == 401
    assert (await client.get('/biblioteca/aplicaciones?q=drawio', headers=auth_catedra)).status_code == 403
    assert (await client.get('/biblioteca/aplicaciones', headers=auth_admin)).status_code == 422
    for query in ['q=drawio', 'q=draw.io', 'q=diagramas', 'categoria=diagramas']:
        result = await client.get('/biblioteca/aplicaciones?' + query, headers=auth_admin)
        assert result.status_code == 200, result.text
        assert result.json()['items'][0]['nombre'] == 'Draw.io'
    empty = await client.get('/biblioteca/aplicaciones?q=otro&categoria=diagramas', headers=auth_admin)
    assert empty.json()['items'] == []


async def test_importar_editar_reimportar_sin_instalar(client, db, auth_admin, fuente):
    from app.models.incorporacion_aplicacion import IncorporacionAplicacion
    from app.models.definicion_servicio import DefinicionServicio
    body = {'identidad_externa': DRAWIO['identidad_externa'], 'revision_fuente': DRAWIO['revision_fuente']}
    headers = auth_admin | {'Idempotency-Key': 'incorporar'}
    first = await client.post('/biblioteca/incorporaciones', json=body, headers=headers)
    assert first.status_code == 201, first.text
    original = first.json()
    replay = await client.post('/biblioteca/incorporaciones', json=body, headers=headers)
    assert replay.json() == original
    edited = await client.patch('/biblioteca/incorporaciones/' + original['id'],
        json={'revision_esperada': original['revision'], 'descripcion': 'Uso académico'},
        headers=auth_admin | {'Idempotency-Key': 'editar'})
    assert edited.status_code == 200, edited.text
    duplicate = await client.post('/biblioteca/incorporaciones', json=body,
        headers=auth_admin | {'Idempotency-Key': 'otra-clave'})
    assert duplicate.status_code == 200
    assert duplicate.json()['descripcion'] == 'Uso académico'
    conflict = await client.patch('/biblioteca/incorporaciones/' + original['id'],
        json={'revision_esperada': original['revision'], 'descripcion': 'No pisar'},
        headers=auth_admin | {'Idempotency-Key': 'editar-conflicto'})
    assert conflict.status_code == 409
    assert await db.scalar(select(func.count()).select_from(IncorporacionAplicacion)) == 1
    assert await db.scalar(select(func.count()).select_from(DefinicionServicio)) == 0
    forbidden = await client.post('/biblioteca/incorporaciones', json=body | {'comando_origen': 'ejecutar'}, headers=headers)
    assert forbidden.status_code == 422


async def test_cursor_invalidado_faltantes_y_producto_no_soportado(client, auth_admin, fuente):
    fuente.items.append({**DRAWIO, 'identidad_externa': 'ct/otra.sh', 'nombre': 'Otra', 'compatibilidad': 'sin_comprobar'})
    first = (await client.get('/biblioteca/aplicaciones?q=a&limit=1', headers=auth_admin)).json()
    assert first['next_cursor']
    altered = await client.get('/biblioteca/aplicaciones?q=drawio&cursor='+first['next_cursor'], headers=auth_admin)
    assert altered.status_code == 409
    assert 'version' in first['items'][0]['faltantes']
