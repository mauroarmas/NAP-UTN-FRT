from uuid import uuid4

from app.models.operacion_infraestructura import OperacionInfraestructura
from tests.capacity_helpers import perfil_capacidad, materializado
from tests import factories


async def test_pending_operation_has_location_scope_and_no_premature_completion(client, db, proxmox, perfil_capacidad, catedra, usuario_catedra, template, auth_catedra):
    service, ledger = await materializado(db, proxmox, catedra, usuario_catedra, template)
    admitted = await client.post(f'/servicios/{service.id}/start', headers=auth_catedra | {'Idempotency-Key': 'scope-start'})
    assert admitted.status_code == 202
    location = admitted.headers['location']
    response = await client.get(location.removeprefix('/api/v1'), headers=auth_catedra)
    assert response.status_code == 200, response.text
    assert response.json()['estado'] == 'pendiente'
    assert response.json()['servicio_id'] == service.id
    assert response.headers['cache-control'] == 'no-store'
    assert 'credenciales' not in response.json()
    foreign = await factories.crear_usuario(db, 'foreign-operation')
    from tests.auth_helpers import headers_para
    denied = await client.get(location.removeprefix('/api/v1'), headers=await headers_para(db, foreign))
    assert denied.status_code == 403 and 'servicio_id' not in denied.json().get('detail', {})


async def test_aliases_do_not_create_incompatible_open_operations(client, db, proxmox, perfil_capacidad, catedra, usuario_catedra, template, auth_admin):
    service, ledger = await materializado(db, proxmox, catedra, usuario_catedra, template)
    first = await client.post(f'/servicios/{service.id}/start', headers=auth_admin | {'Idempotency-Key': 'start'})
    assert first.status_code == 202
    identity = service.id
    for action in ['stop', 'restart', 'reboot']:
        result = await client.post(f'/servicios/{identity}/{action}', headers=auth_admin | {'Idempotency-Key': 'other-' + action})
        assert result.status_code == 409, result.text
        assert result.json()['detail']['operation_id'] == first.json()['operation_id']
    assert not proxmox.detenidos and not proxmox.reiniciados


async def test_restart_alias_replays_one_durable_order(client, db, proxmox, perfil_capacidad, catedra, usuario_catedra, template, auth_admin):
    from app.models.servicio import EstadoServicio
    service, _ = await materializado(db, proxmox, catedra, usuario_catedra, template)
    service.estado = EstadoServicio.RUNNING
    proxmox.recursos[0]['status'] = 'running'
    await db.commit()
    first = await client.post(f'/servicios/{service.id}/restart', headers=auth_admin | {'Idempotency-Key': 'restart-alias'})
    assert first.status_code == 202, first.text
    second = await client.post(f'/servicios/{service.id}/reboot', headers=auth_admin | {'Idempotency-Key': 'restart-alias'})
    assert second.status_code == 202
    assert second.json()['operation_id'] == first.json()['operation_id']
    assert second.headers['idempotency-replayed'] == 'true'
    assert not proxmox.reiniciados


async def test_open_operations_restore_from_authorized_list_and_service_projection(client, db, proxmox, perfil_capacidad, catedra, usuario_catedra, template, auth_catedra):
    service, _ = await materializado(db, proxmox, catedra, usuario_catedra, template)
    accepted = await client.post(f'/servicios/{service.id}/start', headers=auth_catedra | {'Idempotency-Key': 'reload-list'})
    assert accepted.status_code == 202
    listed = await client.get('/operaciones', params={'servicio_id': service.id, 'abiertas': True}, headers=auth_catedra)
    assert listed.status_code == 200
    assert [op['operation_id'] for op in listed.json()['items']] == [accepted.json()['operation_id']]
    services = await client.get('/servicios/', headers=auth_catedra)
    assert services.json()[0]['operation_id'] == accepted.json()['operation_id']
    requests = await client.get('/pedidos/', headers=auth_catedra)
    request = next(p for p in requests.json() if p['id'] == service.pedido_id)
    assert request['operation_id'] == accepted.json()['operation_id']
    detail = await client.get(f'/pedidos/{service.pedido_id}', headers=auth_catedra)
    assert detail.json()['operation_id'] == accepted.json()['operation_id']
    foreign = await factories.crear_usuario(db, 'foreign-list')
    from tests.auth_helpers import headers_para
    headers = await headers_para(db, foreign)
    assert (await client.get('/operaciones', headers=headers)).json()['items'] == []
    assert (await client.get('/operaciones', params={'servicio_id': service.id}, headers=headers)).status_code == 403
    assert (await client.get('/operaciones', params={'cursor': 'invalid-cursor'}, headers=auth_catedra)).status_code == 422
