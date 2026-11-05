from copy import deepcopy
from unittest.mock import AsyncMock
from uuid import UUID

from fastapi import HTTPException
import pytest

from tests.service_helpers import manifest, definition_proof, PRODUCTS


async def create_draft(client, headers, value):
    response = await client.post('/definiciones', headers=headers | {'Idempotency-Key': 'create-' + value['product']},
        json={'codigo': value['definition_key'], 'version': value['definition_version'], 'producto': value['product'], 'modelo_servicio': value['service_model']})
    assert response.status_code == 201, response.text
    return response.json()['id']


async def attach_proof(client, headers, identity, value):
    partial = {k: v for k, v in value.items() if k != 'validation'}
    result = await client.put(f'/definiciones/{identity}/manifest', json={'manifest': partial}, headers=headers | {'Idempotency-Key': 'partial-' + identity})
    assert result.status_code == 200, result.text
    response = await client.post('/evidencias', json=definition_proof(identity, value), headers=headers | {'Idempotency-Key': 'proof-' + identity})
    assert response.status_code == 201, response.text
    value = deepcopy(value)
    value['validation'].update(evidence_id=response.json()['evidencia_ref'], evidence_sha256=response.json()['sha256'])
    result = await client.put(f'/definiciones/{identity}/manifest', json={'manifest': value}, headers=headers | {'Idempotency-Key': 'full-' + identity})
    assert result.status_code == 200, result.text
    return value


@pytest.mark.parametrize('product', list(PRODUCTS))
def test_manifest_schema_and_semantics_cover_three_closed_products(product):
    from app.schemas.definicion import validar_manifest
    value = manifest(product)
    validar_manifest(value)
    for invalid in [{**value, 'command': 'sh'}, {**value, 'resource_type': 'qemu'},
        {**value, 'image': {**value['image'], 'sanitized': False}},
        {**value, 'service_model': 'saas' if product != 'bookstack' else 'iaas'},
        {**value, 'validation': {**value['validation'], 'validated_at': '2026-99-99'}},
        {**value, 'preparation': {**value['preparation'], 'script': '/tmp/arbitrary'}}]:
        with pytest.raises(HTTPException) as exc:
            validar_manifest(invalid)
        assert exc.value.status_code == 422


async def test_draft_partial_manifest_does_not_validate_or_publish(client, auth_admin, auth_catedra):
    value = manifest()
    identity = await create_draft(client, auth_admin, value)
    assert (await client.get('/definiciones', headers=auth_catedra)).json() == []
    partial = await client.put(f'/definiciones/{identity}/manifest', json={'manifest': {'image': {'sha256': 'a' * 64}}}, headers=auth_admin | {'Idempotency-Key': 'partial-only'})
    assert partial.status_code == 200, partial.text
    assert (await client.post(f'/definiciones/{identity}/validar', json={}, headers=auth_admin | {'Idempotency-Key': 'incomplete'})).status_code == 422
    assert (await client.post(f'/definiciones/{identity}/publicar', json={}, headers=auth_admin | {'Idempotency-Key': 'unvalidated'})).status_code == 409
    forbidden = await client.put(f'/definiciones/{identity}/manifest', json={'manifest': {'script': '/tmp/arbitrary'}}, headers=auth_admin | {'Idempotency-Key': 'arbitrary'})
    assert forbidden.status_code == 422
    assert (await client.get(f'/definiciones/{identity}', headers=auth_catedra)).status_code == 403


@pytest.mark.parametrize('product', list(PRODUCTS))
async def test_validation_publication_retirement_and_immutable_version(client, db, auth_admin, auth_catedra, monkeypatch, product):
    from app.services import catalogo_service
    from app.models.definicion_servicio import DefinicionServicio
    availability = AsyncMock()
    monkeypatch.setattr(catalogo_service, 'comprobar_disponibilidad', availability)
    value = manifest(product)
    identity = await create_draft(client, auth_admin, value)
    value = await attach_proof(client, auth_admin, identity, value)
    async def action(name, key):
        return await client.post(f'/definiciones/{identity}/{name}', json={}, headers=auth_admin | {'Idempotency-Key': key})
    validated = await action('validar', 'validate')
    assert validated.status_code == 200, validated.text
    assert validated.json()['estado'] == 'validada' and len(validated.json()['manifest_sha256']) == 64
    invalid_edit = await client.put(f'/definiciones/{identity}/manifest', json={'manifest': value}, headers=auth_admin | {'Idempotency-Key': 'immutable'})
    assert invalid_edit.status_code == 409
    published = await action('publicar', 'publish')
    assert published.status_code == 200, published.text
    assert (await action('publicar', 'publish')).headers['idempotency-replayed'] == 'true'
    offered = (await client.get('/definiciones', headers=auth_catedra)).json()
    assert [row['id'] for row in offered] == [identity]
    assert 'manifest' not in offered[0] and 'image' not in offered[0]
    retired = await client.post(f'/definiciones/{identity}/retirar', json={'motivo': 'Nueva versión para futuras altas'}, headers=auth_admin | {'Idempotency-Key': 'retire'})
    assert retired.status_code == 200, retired.text
    assert (await client.get('/definiciones', headers=auth_catedra)).json() == []
    await db.refresh(await db.get(DefinicionServicio, UUID(identity)))
    row = await db.get(DefinicionServicio, UUID(identity))
    assert row.manifest == value and row.manifest_sha256 == validated.json()['manifest_sha256']
    assert availability.await_count >= 2


async def test_definition_proof_digests_and_artifact_failure_do_not_enable_catalog(client, db, auth_admin, monkeypatch):
    from app.services import catalogo_service
    from app.models.definicion_servicio import DefinicionServicio
    value = manifest('postgresql')
    identity = await create_draft(client, auth_admin, value)
    value = await attach_proof(client, auth_admin, identity, value)
    wrong = deepcopy(value)
    wrong['validation']['evidence_sha256'] = 'f' * 64
    response = await client.put(f'/definiciones/{identity}/manifest', json={'manifest': wrong}, headers=auth_admin | {'Idempotency-Key': 'wrong-digest'})
    assert response.status_code == 200
    response = await client.post(f'/definiciones/{identity}/validar', json={}, headers=auth_admin | {'Idempotency-Key': 'bad-proof'})
    assert response.status_code == 409
    await client.put(f'/definiciones/{identity}/manifest', json={'manifest': value}, headers=auth_admin | {'Idempotency-Key': 'restore-manifest'})
    monkeypatch.setattr(catalogo_service, 'comprobar_disponibilidad', AsyncMock(side_effect=HTTPException(502, detail='Artefacto no comprobable')))
    response = await client.post(f'/definiciones/{identity}/validar', json={}, headers=auth_admin | {'Idempotency-Key': 'missing-artifact'})
    assert response.status_code == 502
    row = await db.get(DefinicionServicio, UUID(identity), populate_existing=True)
    assert row.estado == 'borrador' and row.validada_at is None


async def test_availability_checks_actual_files_network_and_pve_image(tmp_path, monkeypatch, proxmox):
    import hashlib
    from app.config import get_settings
    from app.services.catalogo_service import comprobar_disponibilidad
    value = manifest()
    image, bundle = tmp_path / 'image.tar.zst', tmp_path / 'bundle.py'
    image.write_bytes(b'isolated-test-image'); bundle.write_bytes(b'isolated-test-bundle')
    image.chmod(0o600); bundle.chmod(0o600)
    value['image']['sha256'] = hashlib.sha256(image.read_bytes()).hexdigest()
    value['preparation']['bundle_sha256'] = hashlib.sha256(bundle.read_bytes()).hexdigest()
    settings = get_settings()
    monkeypatch.setattr(settings, 'infrastructure_profile', {'cluster_id': value['validation']['cluster_uuid']})
    monkeypatch.setattr(settings, 'service_artifacts', {'linux-test:1.0.0': {'image_path': str(image), 'bundle_path': str(bundle), 'nodes': ['pve1']}})
    monkeypatch.setattr(settings, 'runner_nodes', {'pve1': {'host': 'unused-test-only.invalid'}})
    monkeypatch.setattr(settings, 'network_profiles', {'test-network': {'bridge': 'vmbr1', 'nodes': ['pve1'],
        'allowed_cidrs': ['192.0.2.0/24'], 'client_cidrs': ['198.51.100.0/24']}})
    proxmox.nodos = [{'node': 'pve1', 'status': 'online'}]
    proxmox.contenidos_storage[('pve1', 'local')] = [{'volid': value['image']['volume_id']}]
    await comprobar_disponibilidad(value)
    image.write_bytes(b'tampered')
    with pytest.raises(HTTPException) as exc:
        await comprobar_disponibilidad(value)
    assert exc.value.status_code == 409
    image.write_bytes(b'isolated-test-image')
    proxmox.contenidos_storage[('pve1', 'local')] = []
    with pytest.raises(HTTPException) as exc:
        await comprobar_disponibilidad(value)
    assert exc.value.status_code == 409
