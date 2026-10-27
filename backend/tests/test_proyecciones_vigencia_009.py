from app.models.pedido import EstadoPedido, ModeloServicio
from app.services.pedido_service import transicionar
from tests.capacity_helpers import perfil_capacidad, materializado


async def test_coverage_actions_hide_secrets_and_disallow_free_expiry(client, db, proxmox, perfil_capacidad,
        catedra, usuario_catedra, template, auth_catedra):
    service, ledger = await materializado(db, proxmox, catedra, usuario_catedra, template)
    service.url_acceso = 'https://legacy.invalid'
    from tests.legacy_helpers import guardar
    await guardar(db,'servicios',service.id,credenciales_acceso={'password':'never-serialize'})
    await db.commit()
    response = await client.get(f'/servicios/{service.id}', headers=auth_catedra)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['cobertura_actual'] and data['estado_cobertura'] == 'con_cobertura'
    assert data['periodos_autorizados'] and data['fin_efectivo_at']
    assert 'start' in data['acciones_habilitadas'] and 'delete' not in data['acciones_habilitadas']
    assert 'credenciales_acceso' not in data and 'url_acceso' not in data
    assert 'never-serialize' not in response.text
    assert (await client.patch(f'/servicios/{service.id}', json={'vence_at': '2030-01-01T00:00:00Z'}, headers=auth_catedra)).status_code == 422


async def test_uncertain_ledger_does_not_offer_start_as_available(client, db, proxmox, perfil_capacidad,
        catedra, usuario_catedra, template, auth_catedra):
    service, ledger = await materializado(db, proxmox, catedra, usuario_catedra, template)
    ledger.estado = 'incierto'
    await db.commit()
    data = (await client.get(f'/servicios/{service.id}', headers=auth_catedra)).json()
    assert not set(data['acciones_habilitadas']) & {'start', 'restart'}
    assert data['motivo_bloqueo'] == 'La asignación requiere reconciliación'


async def test_renewal_correction_uses_historical_product_after_catalog_change(client, db, proxmox, perfil_capacidad,
        catedra, usuario_catedra, template, admin, auth_admin, auth_catedra):
    from app.utils.clock import clock
    from datetime import timedelta
    service, ledger = await materializado(db, proxmox, catedra, usuario_catedra, template)
    service_id = service.id
    start = (clock.now() + timedelta(days=40)).date().isoformat()
    end = (clock.now() + timedelta(days=80)).date().isoformat()
    dates = {'tipo': 'personalizado', 'desde': start, 'hasta': end}
    response = await client.post(f'/servicios/{service_id}/renovar', json={'vigencia': dates},
        headers=auth_catedra | {'Idempotency-Key': 'historical-renewal'})
    assert response.status_code == 201, response.text
    request_id = response.json()['pedido_id']
    await transicionar(db, request_id, EstadoPedido.REQUIERE_AJUSTE, usuario=admin, motivo='Revisar propósito')
    template.activo = False
    template.modelo_servicio = ModeloServicio.SAAS
    await db.commit()
    response = await client.post(f'/pedidos/{request_id}/reenviar', json={'vigencia': dates,
        'descripcion_requerimientos': 'Propósito corregido'}, headers=auth_admin | {'Idempotency-Key': 'historical-correction'})
    assert response.status_code == 200, response.text
    assert response.json()['modelo_servicio'] == 'iaas'
    detail = (await client.get(f'/pedidos/{request_id}', headers=auth_admin)).json()
    assert detail['vigencia'] == dates
