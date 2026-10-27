from datetime import timedelta
from unittest.mock import AsyncMock
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

from app.utils.clock import clock
from tests.capacity_helpers import perfil_capacidad
from tests.service_helpers import manifest
from tests.test_catalogo_definiciones_009 import create_draft, attach_proof


@pytest.fixture
async def published_linux(client, auth_admin, monkeypatch, perfil_capacidad, proxmox):
    from app.services import catalogo_service
    monkeypatch.setattr(catalogo_service, 'comprobar_disponibilidad', AsyncMock())
    value = manifest()
    perfil_capacidad['cluster_id'] = value['validation']['cluster_uuid']
    identity = await create_draft(client, auth_admin, value)
    value = await attach_proof(client, auth_admin, identity, value)
    for action in ['validar', 'publicar']:
        response = await client.post(f'/definiciones/{identity}/{action}', json={}, headers=auth_admin | {'Idempotency-Key': action + '-profile'})
        assert response.status_code == 200, response.text
    proxmox.contenidos_storage[('pve1', 'local')] = [{'volid': value['image']['volume_id'], 'content': 'vztmpl'}]
    return identity, value


def profile(definition_id):
    return {'nombre': 'Linux preparado', 'tipo': 'lxc', 'modelo_servicio': 'iaas',
        'definicion_version_id': definition_id, 'default_vcpus': 1, 'default_ram_mb': 512, 'default_disk_gb': 4}


def dates():
    today = clock.now().astimezone(ZoneInfo('America/Argentina/Tucuman')).date()
    return {'tipo': 'personalizado', 'desde': today.isoformat(), 'hasta': (today + timedelta(days=30)).isoformat()}


async def test_profile_requires_compatible_published_definition_and_minimums(client, auth_admin, published_linux):
    identity, value = published_linux
    for body in [{k: v for k, v in profile(identity).items() if k != 'definicion_version_id'},
        {**profile(identity), 'modelo_servicio': 'paas'}, {**profile(identity), 'default_ram_mb': 128},
        {**profile(identity), 'os_template': 'local:vztmpl/another.tar.zst'}]:
        response = await client.post('/templates/', json=body, headers=auth_admin)
        assert response.status_code == 422, response.text
    response = await client.post('/templates/', json=profile(identity), headers=auth_admin)
    assert response.status_code == 201, response.text
    assert response.json()['definicion_version_id'] == identity and response.json()['oferta_disponible']


async def test_retirement_blocks_new_requests_but_preserves_approval_snapshot(client, db, auth_admin, auth_catedra, catedra, published_linux):
    from app.models.pedido import Pedido
    identity, value = published_linux
    template = (await client.post('/templates/', json=profile(identity), headers=auth_admin)).json()
    body = {'template_id': template['id'], 'modelo_servicio': 'iaas', 'vigencia': dates()}
    response = await client.post('/pedidos/', json=body, headers=auth_catedra | {'Idempotency-Key': 'prepared-request'})
    assert response.status_code == 201, response.text
    pedido_id = response.json()['id']
    selection = {'asignacion': {'template_id': template['id'], 'definicion_version_id': identity,
        'vcpus': 1, 'ram_mb': 512, 'disk_gb': 4}, 'vigencia': dates()}
    evaluated = await client.post(f'/pedidos/{pedido_id}/evaluacion', json=selection, headers=auth_admin)
    assert evaluated.status_code == 200, evaluated.text
    approved = await client.post(f'/pedidos/{pedido_id}/aprobar', json={**selection, 'capacidad_token': evaluated.json()['capacidad_token']}, headers=auth_admin | {'Idempotency-Key': 'prepared-approval'})
    assert approved.status_code == 200, approved.text
    before = approved.json()['asignacion_snapshot']
    retired = await client.post(f'/definiciones/{identity}/retirar', json={'motivo': 'Nueva revisión'}, headers=auth_admin | {'Idempotency-Key': 'retire-profile'})
    assert retired.status_code == 200
    response = await client.post('/pedidos/', json=body, headers=auth_catedra | {'Idempotency-Key': 'unavailable-request'})
    assert response.status_code == 422
    request = await db.get(Pedido, pedido_id, populate_existing=True)
    assert request.asignacion_snapshot == before and request.definicion_version_id == UUID(identity)
    assert (await client.get(f'/definiciones/{identity}', headers=auth_catedra)).status_code == 200
    assert template['id'] not in [row['id'] for row in (await client.get('/templates/', headers=auth_catedra)).json()]
    response = await client.post(f'/servicios/desplegar/{pedido_id}', json={}, headers=auth_admin | {'Idempotency-Key': 'approved-before-retirement'})
    assert response.status_code == 202, response.text


async def test_approval_cannot_select_a_definition_different_from_profile(client, auth_admin, auth_catedra, catedra, published_linux):
    identity, _ = published_linux
    template = (await client.post('/templates/', json=profile(identity), headers=auth_admin)).json()
    body = {'template_id': template['id'], 'modelo_servicio': 'iaas', 'vigencia': dates()}
    request = await client.post('/pedidos/', json=body, headers=auth_catedra | {'Idempotency-Key': 'request-definition'})
    response = await client.post(f"/pedidos/{request.json()['id']}/evaluacion", json={'asignacion': {
        'template_id': template['id'], 'vcpus': 1, 'ram_mb': 512, 'disk_gb': 4}, 'vigencia': dates()}, headers=auth_admin)
    assert response.status_code == 422
