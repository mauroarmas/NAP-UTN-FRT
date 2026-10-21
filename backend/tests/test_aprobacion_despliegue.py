"""Aprobación efectiva y admisión durable; el HTTP no espera a Proxmox."""
from sqlalchemy import select, func
from uuid import UUID

from app.models.pedido import EstadoPedido, Pedido
from app.models.servicio import Servicio
from app.models.compromiso_capacidad import CompromisoCapacidad
from app.models.operacion_infraestructura import OperacionInfraestructura
from tests import factories
from tests.capacity_helpers import perfil_capacidad, seleccion  # noqa:F401


async def evaluate(client, pedido, template, headers):
    payload = seleccion(template)
    response = await client.post(f'/pedidos/{pedido.id}/evaluacion', headers=headers, json=payload)
    assert response.status_code == 200, response.text
    return payload | {'capacidad_token':response.json()['capacidad_token']}


async def test_aprobar_asigna_template_a_pedido_sin_template(
    client, db, catedra, usuario_catedra, template, auth_admin, perfil_capacidad,
):
    pedido = await factories.crear_pedido(db, catedra.id, usuario_catedra.id, None, estado=EstadoPedido.SOLICITADO)
    payload = await evaluate(client, pedido, template, auth_admin)
    response = await client.post(f'/pedidos/{pedido.id}/aprobar', json=payload,
        headers=auth_admin | {'Idempotency-Key':'approve-profile'})
    assert response.status_code == 200, response.text
    await db.refresh(pedido)
    assert pedido.estado == EstadoPedido.APROBADO and pedido.template_id == template.id
    assert response.json()['asignacion_snapshot']['vcpus'] == template.default_vcpus
    ledger = await db.scalar(select(CompromisoCapacidad).where(CompromisoCapacidad.pedido_id == pedido.id))
    assert ledger.vcpus_retenidos == template.default_vcpus and ledger.estado == 'reservado'


async def test_opciones_avanzadas_arbitrarias_no_eluden_seleccion_efectiva(
    client, db, catedra, usuario_catedra, template, auth_admin, perfil_capacidad, proxmox,
):
    pedido = await factories.crear_pedido(db, catedra.id, usuario_catedra.id, template.id, estado=EstadoPedido.SOLICITADO)
    payload = await evaluate(client, pedido, template, auth_admin)
    payload['opciones_avanzadas'] = {'nodo_destino':'otro', 'vlan_tag':100, 'override_vcpus':4}
    response = await client.post(f'/pedidos/{pedido.id}/aprobar', json=payload,
        headers=auth_admin | {'Idempotency-Key':'deny-free-options'})
    assert response.status_code == 422
    assert 'opciones_avanzadas' in response.json()['detail']['campos']
    await db.refresh(pedido)
    assert pedido.estado == EstadoPedido.SOLICITADO
    assert await db.scalar(select(func.count()).select_from(CompromisoCapacidad)) == 0
    assert proxmox.creados == []


async def test_aprobar_con_despliegue_inmediato_encola_sin_io(
    client, db, catedra, usuario_catedra, template, auth_admin, perfil_capacidad, proxmox,
):
    pedido = await factories.crear_pedido(db, catedra.id, usuario_catedra.id, template.id, estado=EstadoPedido.SOLICITADO)
    payload = await evaluate(client, pedido, template, auth_admin)
    response = await client.post(f'/pedidos/{pedido.id}/aprobar',
        json=payload | {'desplegar_inmediatamente':True}, headers=auth_admin | {'Idempotency-Key':'approve-queue'})
    assert response.status_code == 202, response.text
    data = response.json()
    operation = await db.get(OperacionInfraestructura, UUID(data['operation_id']))
    assert operation.estado == 'pendiente' and operation.tipo == 'desplegar'
    await db.refresh(pedido)
    assert pedido.estado == EstadoPedido.EN_DESPLIEGUE
    assert await db.scalar(select(func.count()).select_from(Servicio)) == 0
    assert proxmox.creados == []
    assert not {'url_acceso', 'credenciales_acceso'} & data.keys()
