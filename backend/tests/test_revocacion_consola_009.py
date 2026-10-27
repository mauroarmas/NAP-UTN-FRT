from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.config import get_settings
from app.models.catedra import Catedra
from tests import factories
from tests.fakes import FakeConsoleDirectory
from tests.test_evidence_schema import document


@pytest.fixture
async def native_assignment(db, catedra, usuario_catedra, template, monkeypatch):
    monkeypatch.setattr(get_settings(), 'app_env', 'test')
    usuario_catedra.identidad_consola = 'docente@pve'
    usuario_catedra.inventario_consola = 'asignada'
    usuario_catedra.revision_admin = 1
    catedra.revision_admin = 1
    recipient = await factories.crear_usuario(db, 'nuevo_titular')
    service = await factories.crear_servicio(db, catedra.id, template.id)
    await db.commit()
    native = FakeConsoleDirectory()
    native.permissions['docente@pve'] = {f'/pool/catedra-{catedra.id}'}
    ticket = native.open('docente@pve', f'/pool/catedra-{catedra.id}')
    return SimpleNamespace(catedra_id=catedra.id, old_id=usuario_catedra.id,
        recipient_id=recipient.id, service_id=service.id, native=native, ticket=ticket)


async def request_change(client, assignment, auth_admin):
    return await client.patch(f'/catedras/{assignment.catedra_id}',
        headers=auth_admin | {'Idempotency-Key': 'reassign-1'},
        json={'titular_id': assignment.recipient_id, 'revision_esperada': 1})


async def test_native_revocation_must_be_proven_before_ownership_transfer(client, db, native_assignment, auth_admin, auth_catedra):
    item = native_assignment
    response = await request_change(client, item, auth_admin)
    assert response.status_code == 202, response.text
    change_id = response.json()['cambio_consola_id']
    current = await db.get(Catedra, item.catedra_id, populate_existing=True)
    assert current.titular_id == item.old_id
    denied = await client.get(f'/servicios/{item.service_id}', headers=auth_catedra)
    assert denied.status_code == 403
    assert item.native.allows(item.ticket)  # El portal no declara haber cerrado una consola externa.

    item.native.revoke('docente@pve')  # El operador institucional ejecuta y comprueba este paso.
    assert not item.native.allows(item.ticket)
    proof = document('revocacion_consola')
    proof['resultado']['cambio_consola_id'] = change_id
    evidence = await client.post('/evidencias', headers=auth_admin | {'Idempotency-Key': 'native-proof'}, json=proof)
    assert evidence.status_code == 201, evidence.text
    confirmed = await client.post(f'/admin/cambios-consola/{change_id}/confirmar-revocacion',
        headers=auth_admin | {'Idempotency-Key': 'confirm-native'}, json={'evidencia_ref': evidence.json()['evidencia_ref']})
    assert confirmed.status_code == 200, confirmed.text
    current = await db.get(Catedra, item.catedra_id, populate_existing=True)
    assert current.titular_id == item.recipient_id
    # Una URL/ticket anterior sigue sin poder acceder después de la transferencia.
    assert not item.native.allows(item.ticket)


async def test_failure_and_replay_remain_pending_without_transfer(client, db, native_assignment, auth_admin):
    item = native_assignment
    first = await request_change(client, item, auth_admin)
    assert first.status_code == 202
    second = await request_change(client, item, auth_admin)
    assert second.json()['cambio_consola_id'] == first.json()['cambio_consola_id']
    identity = first.json()['cambio_consola_id']
    failed = await client.post(f'/admin/cambios-consola/{identity}/registrar-fallo',
        headers=auth_admin | {'Idempotency-Key': 'native-failed'}, json={'motivo': 'Operador sin conectividad'})
    assert failed.status_code == 200
    current = await db.get(Catedra, item.catedra_id, populate_existing=True)
    assert current.titular_id == item.old_id
    status = await client.get(f'/admin/cambios-consola/{identity}', headers=auth_admin)
    assert status.json()['estado'] == 'revocacion_fallida'


async def test_wrong_change_proof_or_revision_cannot_complete_transfer(client, native_assignment, auth_admin):
    response = await request_change(client, native_assignment, auth_admin)
    assert response.status_code == 202
    proof = document('revocacion_consola')
    proof['resultado']['cambio_consola_id'] = response.json()['cambio_consola_id']
    proof['resultado']['revision_esperada'] = 2
    invalid = await client.post('/evidencias', headers=auth_admin | {'Idempotency-Key': 'stale-native'}, json=deepcopy(proof))
    assert invalid.status_code == 409


def test_operator_revocation_preserves_other_pools_with_new_session():
    native = FakeConsoleDirectory()
    native.permissions['docente@pve'] = {'/pool/catedra-1', '/pool/catedra-2'}
    old = native.open('docente@pve', '/pool/catedra-1')
    native.revoke('docente@pve', remaining=['/pool/catedra-2'])
    assert not native.allows(old)
    assert native.allows(native.open('docente@pve', '/pool/catedra-2'))
