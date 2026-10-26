from copy import deepcopy

from tests.capacity_helpers import perfil_capacidad, seleccion, preparar_pedido


async def test_evaluation_uses_selected_resources_and_binds_them_to_confirmation(client, db, proxmox, perfil_capacidad, catedra, usuario_catedra, template, auth_admin):
    pedido = await preparar_pedido(db, catedra, usuario_catedra, template)
    payload = seleccion(template)
    payload['asignacion']['vcpus'] = 3
    response = await client.post(f'/pedidos/{pedido.id}/evaluacion', headers=auth_admin, json=payload)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['costo_incremental']['vcpus'] == 3
    assert data['seleccion']['destino'] == payload['destino']
    modified = deepcopy(payload)
    modified['asignacion']['vcpus'] = 4
    response = await client.post(f'/pedidos/{pedido.id}/aprobar', headers=auth_admin | {'Idempotency-Key': 'selection-changed'},
        json={**modified, 'capacidad_token': data['capacidad_token']})
    assert response.status_code == 409, response.text
    assert response.json()['detail']['codigo'] == 'evaluacion_desactualizada'
    await db.refresh(pedido)
    assert pedido.estado.value == 'solicitado'


async def test_confirmation_requires_evaluation_and_retires_read_method(client, db, perfil_capacidad, catedra, usuario_catedra, template, auth_admin):
    pedido = await preparar_pedido(db, catedra, usuario_catedra, template)
    assert (await client.get(f'/pedidos/{pedido.id}/evaluacion', headers=auth_admin)).status_code == 405
    response = await client.post(f'/pedidos/{pedido.id}/aprobar', headers=auth_admin | {'Idempotency-Key': 'no-token'}, json=seleccion(template))
    assert response.status_code == 422
    payload = seleccion(template)
    payload['asignacion']['unprivileged'] = False
    assert (await client.post(f'/pedidos/{pedido.id}/evaluacion', headers=auth_admin, json=payload)).status_code == 422


async def test_approval_replay_keeps_one_commitment_and_authorized_snapshot(client, db, perfil_capacidad, catedra, usuario_catedra, template, auth_admin):
    from sqlalchemy import select, func
    from app.models.compromiso_capacidad import CompromisoCapacidad
    from app.models.vigencia import VigenciaAutorizada
    pedido = await preparar_pedido(db, catedra, usuario_catedra, template)
    payload = seleccion(template)
    evaluation = await client.post(f'/pedidos/{pedido.id}/evaluacion', headers=auth_admin, json=payload)
    assert evaluation.status_code == 200
    body = {**payload, 'capacidad_token': evaluation.json()['capacidad_token']}
    first = await client.post(f'/pedidos/{pedido.id}/aprobar', headers=auth_admin | {'Idempotency-Key': 'same-decision'}, json=body)
    assert first.status_code == 200, first.text
    replay = await client.post(f'/pedidos/{pedido.id}/aprobar', headers=auth_admin | {'Idempotency-Key': 'same-decision'}, json=body)
    assert replay.json() == first.json() and replay.headers['idempotency-replayed'] == 'true'
    assert await db.scalar(select(func.count()).select_from(CompromisoCapacidad)) == 1
    assert await db.scalar(select(func.count()).select_from(VigenciaAutorizada)) == 1


async def test_evaluation_expires_after_sixty_seconds(client, db, perfil_capacidad, catedra, usuario_catedra, template, auth_admin, monkeypatch):
    from app.utils.clock import clock
    from datetime import timedelta
    now = clock.now()
    monkeypatch.setattr(clock, 'now', lambda: now)
    pedido = await preparar_pedido(db, catedra, usuario_catedra, template)
    payload = seleccion(template)
    response = await client.post(f'/pedidos/{pedido.id}/evaluacion', headers=auth_admin, json=payload)
    assert response.status_code == 200, response.text
    token = response.json()['capacidad_token']
    now += timedelta(seconds=61)
    result = await client.post(f'/pedidos/{pedido.id}/aprobar', headers=auth_admin | {'Idempotency-Key': 'expired-evaluation'}, json={**payload, 'capacidad_token': token})
    assert result.status_code == 409, result.text


async def test_oversubscription_needs_reason_but_cannot_override_physical_storage(client, db, proxmox, perfil_capacidad, catedra, usuario_catedra, template, auth_admin):
    pedido = await preparar_pedido(db, catedra, usuario_catedra, template)
    payload = seleccion(template)
    payload['asignacion']['vcpus'] = 8
    evaluation = await client.post(f'/pedidos/{pedido.id}/evaluacion', headers=auth_admin, json=payload)
    assert evaluation.status_code == 200, evaluation.text
    assert evaluation.json()['justificacion_requerida'] is True
    token = evaluation.json()['capacidad_token']
    denied = await client.post(f'/pedidos/{pedido.id}/aprobar', headers=auth_admin | {'Idempotency-Key': 'no-reason'}, json={**payload, 'capacidad_token': token})
    assert denied.status_code == 409
    await db.refresh(pedido)
    approved = await client.post(f'/pedidos/{pedido.id}/aprobar', headers=auth_admin | {'Idempotency-Key': 'with-reason'}, json={**payload, 'capacidad_token': token, 'justificacion_capacidad': 'Carga didáctica controlada'})
    assert approved.status_code == 200, approved.text
    second = await preparar_pedido(db, catedra, usuario_catedra, template)
    payload = seleccion(template)
    proxmox.storages[0]['avail'] = 1024 ** 3
    evaluated = await client.post(f'/pedidos/{second.id}/evaluacion', headers=auth_admin, json=payload)
    assert evaluated.status_code == 200, evaluated.text
    physical = await client.post(f'/pedidos/{second.id}/aprobar', headers=auth_admin | {'Idempotency-Key': 'physical-limit'},
        json={**payload, 'capacidad_token': evaluated.json()['capacidad_token'], 'justificacion_capacidad': 'No elude un límite físico'})
    assert physical.status_code == 409
    assert physical.json()['detail']['codigo'] == 'limite_fisico'


async def test_telemetria_normal_no_invalida_aprobacion(client, db, proxmox, perfil_capacidad, catedra, usuario_catedra, template, auth_admin):
    pedido = await preparar_pedido(db, catedra, usuario_catedra, template)
    payload = seleccion(template)
    evaluated = await client.post(f'/pedidos/{pedido.id}/evaluacion', headers=auth_admin, json=payload)
    assert evaluated.status_code == 200
    # Reproduce la VM real: cambia RAM usada por el host y algunos bytes de disco,
    # sin modificar recursos configurados, compromisos ni elegibilidad del pedido.
    proxmox.nodos[0]['mem'] += 3 * 1024**2
    proxmox.storages[0]['avail'] -= 4096
    approved = await client.post(f'/pedidos/{pedido.id}/aprobar', headers=auth_admin | {'Idempotency-Key': 'telemetria-estable'},
        json={**evaluated.json()['seleccion'], 'capacidad_token': evaluated.json()['capacidad_token']})
    assert approved.status_code == 200, approved.text


async def test_perder_espacio_fisico_sigue_impidiendo_aprobar(client, db, proxmox, perfil_capacidad, catedra, usuario_catedra, template, auth_admin):
    from sqlalchemy import select, func
    from app.models.compromiso_capacidad import CompromisoCapacidad
    pedido = await preparar_pedido(db, catedra, usuario_catedra, template)
    evaluated = await client.post(f'/pedidos/{pedido.id}/evaluacion', headers=auth_admin, json=seleccion(template))
    assert evaluated.status_code == 200
    proxmox.storages[0]['avail'] = 1024**3
    denied = await client.post(f'/pedidos/{pedido.id}/aprobar', headers=auth_admin | {'Idempotency-Key': 'sin-disco-fisico'},
        json={**evaluated.json()['seleccion'], 'capacidad_token': evaluated.json()['capacidad_token']})
    assert denied.status_code == 409
    assert await db.scalar(select(func.count()).select_from(CompromisoCapacidad)) == 0
    await db.refresh(pedido)
    assert pedido.estado.value == 'solicitado'
