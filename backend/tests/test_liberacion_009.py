from datetime import timedelta

from sqlalchemy import select

from app.models.compromiso_capacidad import CompromisoCapacidad
from app.models.operacion_infraestructura import OperacionInfraestructura
from app.models.vigencia import VigenciaAutorizada
from app.models.pedido import PedidoHistorial
from tests.capacity_helpers import perfil_capacidad, preparar_pedido, seleccion


async def approved(client, db, category, user, template, headers):
    pedido = await preparar_pedido(db, category, user, template)
    payload = seleccion(template)
    result = await client.post(f'/pedidos/{pedido.id}/evaluacion', headers=headers, json=payload)
    assert result.status_code == 200, result.text
    result = await client.post(f'/pedidos/{pedido.id}/aprobar', headers=headers | {'Idempotency-Key': 'approval'}, json={**payload, 'capacidad_token': result.json()['capacidad_token']})
    assert result.status_code == 200, result.text
    return pedido


async def test_revert_replays_without_erasing_assignment_or_releasing_twice(client, db, perfil_capacidad, catedra, usuario_catedra, template, auth_admin):
    pedido = await approved(client, db, catedra, usuario_catedra, template, auth_admin)
    original_assignment=dict(pedido.asignacion_snapshot)
    identity = pedido.id
    first = await client.post(f'/pedidos/{identity}/revertir-aprobacion', headers=auth_admin | {'Idempotency-Key': 'revert'}, json={'motivo': 'Cambio institucional'})
    assert first.status_code == 200, first.text
    second = await client.post(f'/pedidos/{identity}/revertir-aprobacion', headers=auth_admin | {'Idempotency-Key': 'revert'}, json={'motivo': 'Cambio institucional'})
    assert second.json() == first.json()
    assert second.headers['idempotency-replayed'] == 'true'
    await db.refresh(pedido)
    assert pedido.asignacion_snapshot == original_assignment
    ledger = await db.scalar(select(CompromisoCapacidad))
    assert ledger.estado == 'liberado' and ledger.vcpus_retenidos == 0
    period = await db.scalar(select(VigenciaAutorizada))
    assert period.revocada_at is not None
    history = (await db.scalars(select(PedidoHistorial).where(PedidoHistorial.estado_anterior == 'aprobado'))).all()
    assert len(history) == 1


async def test_uncertain_dispatch_cannot_release_through_revert_adjust_or_soft_delete(client, db, perfil_capacidad, catedra, usuario_catedra, template, auth_admin):
    pedido = await approved(client, db, catedra, usuario_catedra, template, auth_admin)
    identity = pedido.id
    result = await client.post(f'/servicios/desplegar/{identity}', headers=auth_admin | {'Idempotency-Key': 'dispatch'}, json={})
    assert result.status_code == 202
    operation = await db.scalar(select(OperacionInfraestructura))
    operation.estado, operation.fase = 'incierta', 'dispatch_started'
    ledger = await db.scalar(select(CompromisoCapacidad))
    ledger.estado = 'incierto'
    await db.commit()
    for action, body in [('revertir-aprobacion', {'motivo': 'No debe liberar'}), ('solicitar-ajuste', {'observaciones': 'No debe liberar'})]:
        denied = await client.post(f'/pedidos/{identity}/{action}', headers=auth_admin | {'Idempotency-Key': action}, json=body)
        assert denied.status_code == 409, denied.text
    denied = await client.delete(f'/pedidos/{identity}', headers=auth_admin | {'Idempotency-Key': 'delete-uncertain'})
    assert denied.status_code == 409
    await db.refresh(ledger)
    assert ledger.liberado_at is None and ledger.vcpus_retenidos > 0 and ledger.disk_bytes_retenidos > 0


async def test_expiry_cancels_queued_preparation_once_and_retains_revoked_period(client, db, perfil_capacidad, catedra, usuario_catedra, template, auth_admin, monkeypatch):
    from app.utils.clock import clock
    from app.services.capacidad_service import expirar_reservas
    instant = clock.now()
    monkeypatch.setattr(clock, 'now', lambda: instant)
    pedido = await approved(client, db, catedra, usuario_catedra, template, auth_admin)
    result = await client.post(f'/servicios/desplegar/{pedido.id}', headers=auth_admin | {'Idempotency-Key': 'queued'}, json={})
    assert result.status_code == 202
    instant += timedelta(days=2)
    assert (await expirar_reservas(db))['afectados'] == 1
    assert (await expirar_reservas(db))['afectados'] == 0
    operation = await db.scalar(select(OperacionInfraestructura))
    assert operation.estado == 'fallida' and operation.error_codigo == 'cancelada_antes_dispatch'
    period = await db.scalar(select(VigenciaAutorizada))
    assert period.revocada_at and period.desde_local < period.hasta_local


async def test_adjustment_revokes_old_decision_and_new_approval_keeps_history(client, db, perfil_capacidad, catedra, usuario_catedra, template, auth_admin):
    pedido = await approved(client, db, catedra, usuario_catedra, template, auth_admin)
    identity = pedido.id
    adjusted = await client.post(f'/pedidos/{identity}/solicitar-ajuste', headers=auth_admin | {'Idempotency-Key': 'adjust'}, json={'observaciones': 'Adecuar vigencia'})
    assert adjusted.status_code == 200, adjusted.text
    assert adjusted.json()['estado'] == 'requiere_ajuste'
    resent = await client.post(f'/pedidos/{identity}/reenviar', headers=auth_admin | {'Idempotency-Key': 'resend'}, json={'vigencia':seleccion(template)['vigencia']})
    assert resent.status_code == 200, resent.text
    payload = seleccion(template)
    evaluated = await client.post(f'/pedidos/{identity}/evaluacion', headers=auth_admin, json=payload)
    assert evaluated.status_code == 200
    result = await client.post(f'/pedidos/{identity}/aprobar', headers=auth_admin | {'Idempotency-Key': 'approval-new'}, json={**payload, 'capacidad_token': evaluated.json()['capacidad_token']})
    assert result.status_code == 200, result.text
    periods = (await db.scalars(select(VigenciaAutorizada).order_by(VigenciaAutorizada.revision_decision))).all()
    assert [row.revision_decision for row in periods] == [1, 2]
    assert periods[0].revocada_at and periods[1].revocada_at is None
    ledgers = (await db.scalars(select(CompromisoCapacidad))).all()
    assert sorted(row.estado for row in ledgers) == ['liberado', 'reservado']
