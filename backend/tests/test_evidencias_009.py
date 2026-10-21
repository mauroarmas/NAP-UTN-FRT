"""Registro inmutable, tipado y autorizado de evidencias administrativas."""

from copy import deepcopy
from datetime import timedelta, datetime, timezone

import pytest

from tests.test_evidence_schema import document


@pytest.fixture(autouse=True)
def isolated_evidence_environment(monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), 'app_env', 'test')


@pytest.fixture
async def evidence_definition(db):
    from app.models.definicion_servicio import DefinicionServicio
    row = DefinicionServicio(codigo='postgresql16', version='1', producto='postgresql',
                            modelo_servicio='paas', manifest={}, estado='borrador')
    db.add(row)
    await db.commit()
    return row


@pytest.fixture
def evidence_document(evidence_definition):
    value = document()
    value['resultado']['definicion_id'] = str(evidence_definition.id)
    return value


async def test_teacher_cannot_import_or_read_evidence(client, auth_catedra):
    response = await client.post('/evidencias', headers=auth_catedra | {'Idempotency-Key': 'denied'}, json=document())
    assert response.status_code == 403
    response = await client.get('/evidencias/01900000-0000-4000-8000-000000000001', headers=auth_catedra)
    assert response.status_code == 403


async def test_import_is_immutable_and_replayed_with_same_reference(client, auth_admin, evidence_document):
    headers = auth_admin | {'Idempotency-Key': 'import-evidence'}
    first = await client.post('/evidencias', headers=headers, json=evidence_document)
    assert first.status_code == 201, first.text
    second = await client.post('/evidencias', headers=headers, json=evidence_document)
    assert second.status_code == 201
    assert first.json() == second.json()
    assert second.headers['Idempotency-Replayed'] == 'true'
    ref = first.json()['evidencia_ref']
    stored = await client.get(f'/evidencias/{ref}', headers=auth_admin)
    assert stored.status_code == 200
    assert stored.json()['documento'] == evidence_document
    assert stored.headers['cache-control'] == 'no-store'
    changed = await client.patch(f'/evidencias/{ref}', headers=auth_admin, json={})
    assert changed.status_code == 405


@pytest.mark.parametrize('change', ['extra', 'future', 'uuid', 'float', 'revision'])
async def test_invalid_documents_never_create_evidence(client, auth_admin, evidence_document, change):
    value = deepcopy(evidence_document)
    if change == 'extra':
        value['registrada_por'] = 999
    elif change == 'future':
        value['observado_at'] = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat().replace('+00:00', 'Z')
    elif change == 'uuid':
        value['resultado']['definicion_id'] = '01900000-0000-4000-8000-000000000099'
    elif change == 'float':
        value['schema_version'] = 1.0
    else:
        value['resultado']['definition_version'] = 'otra-version'
    response = await client.post('/evidencias', headers=auth_admin | {'Idempotency-Key': 'invalid-' + change}, json=value)
    assert response.status_code in {409, 422}


async def test_duplicate_keys_and_oversized_documents_are_rejected(client, auth_admin):
    headers = auth_admin | {'Idempotency-Key': 'raw', 'Content-Type': 'application/json'}
    duplicate = await client.post('/evidencias', headers=headers, content='{"tipo":"acceso_instancia","tipo":"revocacion_consola"}')
    assert duplicate.status_code == 422
    large = await client.post('/evidencias', headers=headers, content=' ' * (65536 + 1))
    assert large.status_code == 413


async def test_simulation_cannot_be_imported_in_production(client, auth_admin, evidence_document, monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), 'app_env', 'production')
    response = await client.post('/evidencias', headers=auth_admin | {'Idempotency-Key': 'simulation'}, json=evidence_document)
    assert response.status_code == 422


async def test_database_tampering_is_detected_on_read(client, auth_admin, evidence_document, db):
    from sqlalchemy import text
    response = await client.post('/evidencias', headers=auth_admin | {'Idempotency-Key': 'tamper'}, json=evidence_document)
    assert response.status_code == 201
    reference = response.json()['evidencia_ref']
    # Simular un ataque directo al almacenamiento, fuera del servicio append-only.
    await db.execute(text("UPDATE evidencias SET documento_canonico = '{}' WHERE id = :id"),
                     {'id': reference.replace('-', '')})
    await db.commit()
    altered = await client.get('/evidencias/' + reference, headers=auth_admin)
    assert altered.status_code == 409


@pytest.fixture
async def evidence_console_change(db, usuario_catedra, catedra, admin):
    from app.models.cambio_acceso_consola import CambioAccesoConsola
    row = CambioAccesoConsola(accion='reasignar', usuario_id=usuario_catedra.id,
        catedra_id=catedra.id, revision_esperada=1, identidad_nativa='docente@pve',
        scopes_anteriores=['/pool/catedra-1'], scopes_propuestos=[],
        cambio_propuesto={'titular_id': admin.id}, solicitada_por=admin.id)
    db.add(row)
    await db.commit()
    return row


async def test_console_evidence_is_bound_to_change_identity_and_revision(client, auth_admin, evidence_console_change):
    value = document('revocacion_consola')
    value['resultado']['cambio_consola_id'] = str(evidence_console_change.id)
    headers = auth_admin | {'Idempotency-Key': 'console-proof'}
    response = await client.post('/evidencias', headers=headers, json=value)
    assert response.status_code == 201, response.text
    value['resultado']['revision_esperada'] = 2
    response = await client.post('/evidencias', headers=auth_admin | {'Idempotency-Key': 'stale-proof'}, json=value)
    assert response.status_code == 409


async def test_unknown_instance_proof_does_not_substitute_a_definition_proof(client, auth_admin):
    response = await client.post('/evidencias', headers=auth_admin | {'Idempotency-Key': 'unknown-instance'},
                                 json=document('acceso_instancia'))
    assert response.status_code == 422


@pytest.fixture
async def prepared_instance_document(db, catedra, admin, template, evidence_definition, monkeypatch):
    import hashlib
    from uuid import uuid4
    from cryptography.fernet import Fernet
    from app.config import get_settings
    from app.models.identidad_infraestructura import IdentidadInfraestructura
    from app.models.operacion_infraestructura import OperacionInfraestructura
    from app.utils.secretos import configured_keyring
    from tests.factories import crear_pedido, crear_servicio

    settings = get_settings()
    monkeypatch.setattr(settings, 'secret_keyring', {'test': Fernet.generate_key().decode()})
    monkeypatch.setattr(settings, 'secret_active_key', 'test')
    pedido = await crear_pedido(db, catedra.id, admin.id, template.id)
    service = await crear_servicio(db, catedra.id, template.id, pedido_id=pedido.id)
    resource_uuid = uuid4()
    identity = IdentidadInfraestructura(cluster_id=str(uuid4()), vmid=900, nodo='pve1',
        pool_catedra='catedra-test', resource_uuid=resource_uuid, pedido_alta_id=pedido.id,
        servicio_id=service.id, estado='materializada',
        nonce_cifrado=configured_keyring().encrypt('nonce-de-prueba', context=f'infra:{resource_uuid}:nonce'))
    db.add(identity)
    await db.flush()
    service.identidad_infraestructura_id = identity.id
    service.definicion_version_id = evidence_definition.id
    service.acceso_metadata = {'endpoint': 'postgresql://base.example.edu:5432/curso'}
    operation = OperacionInfraestructura(tipo='desplegar', pedido_id=pedido.id, servicio_id=service.id,
        identidad_infraestructura_id=identity.id, actor_usuario_id=admin.id, actor_id_normalizado=str(admin.id),
        idempotency_key='test-prepared-instance', request_hash='a' * 64, estado='confirmada',
        confirmada_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    db.add(operation)
    await db.commit()
    value = document('acceso_instancia')
    value['resultado'].update(servicio_id=service.id, definicion_id=str(evidence_definition.id),
        resource_uuid=str(resource_uuid), nonce_sha256=hashlib.sha256(b'nonce-de-prueba').hexdigest(),
        preparacion_id=str(operation.id), endpoint=service.acceso_metadata['endpoint'],
        pruebas=['conexion_autenticada', 'escritura_lectura', 'persistencia'])
    return value


async def test_instance_evidence_requires_current_nonce_preparation_and_function(client, auth_admin, prepared_instance_document):
    value = prepared_instance_document
    response = await client.post('/evidencias', headers=auth_admin | {'Idempotency-Key': 'instance-proof'}, json=value)
    assert response.status_code == 201, response.text
    for key, new_value, status in [('nonce_sha256', 'c' * 64, 409),
                                   ('pruebas', ['conexion_autenticada'], 422),
                                   ('endpoint', 'postgresql://otro.example.edu:5432/curso', 409)]:
        bad = deepcopy(value)
        bad['resultado'][key] = new_value
        response = await client.post('/evidencias', headers=auth_admin | {'Idempotency-Key': 'bad-' + key}, json=bad)
        assert response.status_code == status, response.text
