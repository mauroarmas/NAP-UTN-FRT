import pytest

from app.models.pedido import EstadoPedido
from app.utils.security import create_access_token, decode_access_token
from tests.auth_helpers import headers_para
from tests import factories
from tests.capacity_helpers import seleccion, perfil_capacidad  # noqa:F401
from app.models.compromiso_capacidad import CompromisoCapacidad
from sqlalchemy import select, func


@pytest.mark.parametrize('action', ['reenviar', 'cancelar'])
@pytest.mark.parametrize('own', [True, False])
async def test_teacher_cannot_mutate_own_or_foreign_request(client, db, catedra, usuario_catedra, auth_catedra, template, admin, action, own):
    category = catedra if own else await factories.crear_catedra(db, nombre='Otra', titular_id=admin.id)
    pedido = await factories.crear_pedido(db, category.id, usuario_catedra.id, template.id, estado=EstadoPedido.REQUIERE_AJUSTE)
    before = pedido.descripcion_requerimientos
    payload = {'descripcion_requerimientos': 'No aplicar'} if action == 'reenviar' else {'motivo': 'Prueba'}
    response = await client.post(f'/pedidos/{pedido.id}/{action}', headers=auth_catedra | {'Idempotency-Key': 'denied-' + action}, json=payload)
    assert response.status_code == 403
    await db.refresh(pedido)
    assert pedido.estado == EstadoPedido.REQUIERE_AJUSTE
    assert pedido.descripcion_requerimientos == before


@pytest.mark.parametrize('action', ['reenviar', 'cancelar'])
async def test_admin_can_execute_named_action(client, db, catedra, usuario_catedra, auth_admin, template, action, perfil_capacidad):
    pedido = await factories.crear_pedido(db, catedra.id, usuario_catedra.id, template.id, estado=EstadoPedido.REQUIERE_AJUSTE)
    payload = {'vigencia':seleccion(template)['vigencia']} if action == 'reenviar' else {'motivo': 'Decisión administrativa'}
    response = await client.post(f'/pedidos/{pedido.id}/{action}', headers=auth_admin | {'Idempotency-Key': 'admin-' + action}, json=payload)
    assert response.status_code == 200, response.text
    expected = EstadoPedido.SOLICITADO if action == 'reenviar' else EstadoPedido.CANCELADO
    assert response.json()['estado'] == expected.value


async def test_claimed_admin_role_does_not_override_database_role(client, db, catedra, usuario_catedra, template):
    pedido = await factories.crear_pedido(db, catedra.id, usuario_catedra.id, template.id, estado=EstadoPedido.REQUIERE_AJUSTE)
    headers = await headers_para(db, usuario_catedra)
    claims = decode_access_token(headers['Cookie'].split('=', 1)[1])
    token = create_access_token({**claims, 'rol': 'admin'})
    headers['Cookie'] = 'nap_session=' + token
    response = await client.post(f'/pedidos/{pedido.id}/cancelar', headers=headers, json={'motivo': 'No autorizado'})
    assert response.status_code == 403


async def test_generic_state_patch_is_retired_even_for_admin(client, db, catedra, admin, auth_admin, template):
    pedido = await factories.crear_pedido(db, catedra.id, admin.id, template.id, estado=EstadoPedido.SOLICITADO)
    response = await client.patch(f'/pedidos/{pedido.id}/estado', headers=auth_admin, json={'estado': 'aprobado'})
    assert response.status_code == 405
    await db.refresh(pedido)
    assert pedido.estado == EstadoPedido.SOLICITADO
    assert await db.scalar(select(func.count()).select_from(CompromisoCapacidad)) == 0
