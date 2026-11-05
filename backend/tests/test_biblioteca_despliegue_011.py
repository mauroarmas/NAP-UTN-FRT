"""Tests for US2: Docker Hub discovery replacing Community Scripts."""
import json
from uuid import uuid4
import httpx
import pytest
from sqlalchemy import select, func

from app.models.incorporacion_aplicacion import IncorporacionAplicacion
from app.models.configuracion_despliegue import ConfiguracionDespliegue
from app.models.compromiso_capacidad import CompromisoCapacidad
from app.models.identidad_infraestructura import IdentidadInfraestructura
from app.services import biblioteca_service
from tests.test_templates_aplicaciones_011 import catalog_image, app_order, approve, perfil_capacidad, red_aplicaciones_011, profile_entry


HUB_RESULTS_PAGE_1 = {
    'count': 3,
    'next': 'https://hub.docker.com/v2/search/repositories/?page=2&page_size=2&query=whoami',
    'previous': None,
    'results': [
        {
            'repo_name': 'traefik/whoami',
            'short_description': 'Tiny Go webserver that prints OS information and HTTP request to output',
            'star_count': 72,
            'pull_count': 45234400,
            'is_automated': False,
            'is_official': False,
        },
        {
            'repo_name': 'library/ubuntu',
            'short_description': 'Ubuntu is a Debian-based Linux operating system',
            'star_count': 16000,
            'pull_count': 1000000000,
            'is_automated': False,
            'is_official': True,
        },
    ],
}

HUB_RESULTS_PAGE_2 = {
    'count': 3,
    'next': None,
    'previous': 'https://hub.docker.com/v2/search/repositories/?page=1&page_size=2&query=whoami',
    'results': [
        {
            'repo_name': 'stefanscherer/whoami',
            'short_description': 'whoami multi-arch image',
            'star_count': 19,
            'pull_count': 1596992,
            'is_automated': False,
            'is_official': False,
        },
    ],
}


@pytest.fixture
def fake_docker_hub(monkeypatch):
    calls = []

    async def mock_search(query, *, page=1, page_size=20):
        calls.append({'query': query, 'page': page, 'page_size': page_size})
        if query == '__rate_limit__':
            raise biblioteca_service.DockerHubRateLimitError()
        if query == '__unavailable__':
            raise biblioteca_service.DockerHubUnavailableError()
        if query == 'vacio':
            return {'count': 0, 'results': [], 'next': None, 'previous': None}
        if page == 1:
            return HUB_RESULTS_PAGE_1
        return HUB_RESULTS_PAGE_2

    monkeypatch.setattr(biblioteca_service, 'docker_hub_search', mock_search)
    return calls


async def test_busqueda_autorizacion_y_campos_requeridos(client, auth_admin, auth_catedra, fake_docker_hub):
    # Sin autenticación -> 401
    assert (await client.get('/biblioteca/aplicaciones?q=whoami')).status_code == 401
    # Rol docente/cátedra -> 403
    assert (await client.get('/biblioteca/aplicaciones?q=whoami', headers=auth_catedra)).status_code == 403
    # Admin sin parámetros de búsqueda -> 422
    assert (await client.get('/biblioteca/aplicaciones', headers=auth_admin)).status_code == 422


async def test_busqueda_docker_hub_exito_y_formato_items(client, auth_admin, fake_docker_hub):
    response = await client.get('/biblioteca/aplicaciones?q=whoami', headers=auth_admin)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['fuente']['proveedor'] == 'docker_hub'
    assert len(data['items']) == 2
    item1 = data['items'][0]
    assert item1['nombre'] == 'traefik/whoami'
    assert item1['repositorio'] == 'traefik/whoami'
    assert item1['referencia'] == 'traefik/whoami:latest'
    assert item1['descripcion'] == 'Tiny Go webserver that prints OS information and HTTP request to output'
    assert item1['procedencia'] == 'comunidad'
    assert 'oficial' not in item1['distintivos']

    item2 = data['items'][1]
    assert item2['procedencia'] == 'oficial'
    assert 'oficial' in item2['distintivos']


async def test_busqueda_paginacion_cursor_y_tamper_rejected(client, auth_admin, fake_docker_hub):
    first = (await client.get('/biblioteca/aplicaciones?q=whoami&limit=2', headers=auth_admin)).json()
    assert first['next_cursor'] is not None

    second = (await client.get(f"/biblioteca/aplicaciones?q=whoami&cursor={first['next_cursor']}", headers=auth_admin)).json()
    assert len(second['items']) == 1
    assert second['items'][0]['nombre'] == 'stefanscherer/whoami'
    assert second['next_cursor'] is None

    # Cursor manipulado o con búsqueda alterada -> 409
    tampered = await client.get(f"/biblioteca/aplicaciones?q=otra_busqueda&cursor={first['next_cursor']}", headers=auth_admin)
    assert tampered.status_code == 409
    assert tampered.json()['detail']['codigo'] == 'cursor_desactualizado'


async def test_busqueda_cero_resultados_vs_errores_proveedor(client, auth_admin, fake_docker_hub):
    # Cero resultados es 200 con lista vacía
    empty = await client.get('/biblioteca/aplicaciones?q=vacio', headers=auth_admin)
    assert empty.status_code == 200
    assert empty.json()['items'] == []
    assert empty.json()['next_cursor'] is None

    # Rate limit de Docker Hub -> 429
    limited = await client.get('/biblioteca/aplicaciones?q=__rate_limit__', headers=auth_admin)
    assert limited.status_code == 429
    assert limited.json()['detail']['codigo'] == 'limite_consultas_proveedor'

    # Docker Hub no disponible / error de red -> 502
    unavail = await client.get('/biblioteca/aplicaciones?q=__unavailable__', headers=auth_admin)
    assert unavail.status_code == 502
    assert unavail.json()['detail']['codigo'] == 'proveedor_no_disponible'


async def test_categorias_docker_hub_no_bloqueantes(client, auth_admin):
    # Categorías devuelve lista vacía segura sin error
    response = await client.get('/biblioteca/categorias', headers=auth_admin)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data['items'], list)
    assert data['fuente']['proveedor'] == 'docker_hub'


async def test_rechazo_nuevos_community_scripts_preservando_lectura_legacy(client, db, auth_admin, admin):
    # Insertamos un registro legacy en la DB para verificar preservación
    legacy_row = IncorporacionAplicacion(
        id=uuid4(),
        proveedor='community-scripts',
        identidad_externa='ct/drawio.sh',
        revision_fuente='a' * 40,
        comando_sha256='b' * 64,
        comando_origen='bash -c drawio',
        url_origen='https://community-scripts.github.io/ct/drawio.sh',
        origen_clave='v1.0.0',
        nombre='Draw.io Histórico',
        descripcion='Diagramas legacy',
        categorias=['diagramas'],
        aliases=['diagrams'],
        datos_origen={'compatibilidad': 'adaptador_disponible'},
        revision=1,
        creado_por=admin.id,
    )
    db.add(legacy_row)
    await db.commit()

    # GET /biblioteca/incorporaciones lista el elemento legacy
    listing = await client.get('/biblioteca/incorporaciones', headers=auth_admin)
    assert listing.status_code == 200
    items = listing.json()['items']
    assert any(i['identidad_externa'] == 'ct/drawio.sh' for i in items)

    # GET /biblioteca/incorporaciones/{id} obtiene el elemento legacy
    detail = await client.get(f'/biblioteca/incorporaciones/{legacy_row.id}', headers=auth_admin)
    assert detail.status_code == 200
    assert detail.json()['nombre'] == 'Draw.io Histórico'

    # POST /biblioteca/incorporaciones se rechaza para altas nuevas
    rejected = await client.post(
        '/biblioteca/incorporaciones',
        headers=auth_admin | {'Idempotency-Key': 'legacy-reject'},
        json={'identidad_externa': 'ct/nuevo.sh', 'revision_fuente': 'c' * 40},
    )
    assert rejected.status_code == 422
    assert rejected.json()['detail']['codigo'] in {'community_scripts_retirado', 'origen_no_admitido'}


async def test_seleccion_hub_alta_propia_idempotente_sin_ct(client, db, auth_admin, app_order, catalog_image, proxmox):
    # Selección de imagen desde Hub se envía al POST /templates/aplicaciones existente
    calls, _ = catalog_image
    body = {
        'nombre': 'Whoami Servicio',
        'imagen': 'traefik/whoami:latest',
        'puerto': 80,
        'descripcion': 'Tiny Go webserver',
        'persistencia': ['/data'],
    }
    response = await client.post(
        '/templates/aplicaciones',
        headers=auth_admin | {'Idempotency-Key': 'whoami-alta-hub'},
        json=body,
    )
    assert response.status_code == 201, response.text
    assert response.json()['oferta_disponible'] is True
    assert response.json()['estado_presentacion'] == 'Disponible para solicitar'

    # Cero CTs creados, cero compromisos de capacidad
    assert await db.scalar(select(func.count()).select_from(CompromisoCapacidad)) == 0
    assert await db.scalar(select(func.count()).select_from(IdentidadInfraestructura)) == 0
    assert not proxmox.creados
