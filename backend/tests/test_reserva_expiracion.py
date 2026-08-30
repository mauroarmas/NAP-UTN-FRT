"""Expiración de reservas: la capacidad comprometida tampoco queda huérfana.

Un pedido aprobado que nunca se despliega retendría capacidad para siempre. Es
la misma clase de fuga silenciosa que un contenedor sin registro, solo que sin
contenedor que encontrar.
"""

from datetime import datetime, timedelta

import pytest

from app.models.pedido import EstadoPedido, PedidoHistorial
from app.services import capacidad_service
from sqlalchemy import select
from tests import factories

NODO = [
    {
        "node": "pve1",
        "status": "online",
        "cpu": 0.1,
        "maxcpu": 8,
        "maxmem": 16 * 1024**3,
        "maxdisk": 100 * 1024**3,
    }
]


@pytest.fixture(autouse=True)
def cluster(proxmox):
    proxmox.nodos = NODO
    return proxmox


async def _aprobado(client, db, catedra, usuario, template, auth_admin):
    pedido = await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario.id,
        template_id=template.id,
        estado=EstadoPedido.SOLICITADO,
    )
    r = await client.post(f"/pedidos/{pedido.id}/aprobar", json={}, headers=auth_admin)
    assert r.status_code == 200, r.text
    await db.refresh(pedido)
    return pedido


async def test_aprobar_fija_un_vencimiento_a_la_reserva(
    client, db, catedra, usuario_catedra, template, auth_admin
):
    pedido = await _aprobado(client, db, catedra, usuario_catedra, template, auth_admin)

    assert pedido.reserva_expira_at is not None
    assert pedido.reserva_vcpus == template.default_vcpus


async def test_la_reserva_vencida_libera_la_capacidad(
    client, db, catedra, usuario_catedra, template, auth_admin
):
    pedido = await _aprobado(client, db, catedra, usuario_catedra, template, auth_admin)

    con_reserva = await capacidad_service.panorama(db)
    assert con_reserva["reservado"]["vcpus"] == template.default_vcpus

    # Se adelanta el vencimiento en lugar de esperar 24 horas.
    pedido.reserva_expira_at = datetime.utcnow() - timedelta(minutes=1)
    await db.commit()

    resultado = await capacidad_service.expirar_reservas(db)

    assert resultado["afectados"] == 1
    liberada = await capacidad_service.panorama(db)
    assert liberada["reservado"]["vcpus"] == 0
    assert liberada["libre"]["vcpus"] == con_reserva["libre"]["vcpus"] + template.default_vcpus


async def test_la_expiracion_queda_registrada_con_el_sistema_como_autor(
    client, db, catedra, usuario_catedra, template, auth_admin
):
    """La transición no se atribuye a ninguna persona ni se omite del historial."""
    pedido = await _aprobado(client, db, catedra, usuario_catedra, template, auth_admin)
    pedido.reserva_expira_at = datetime.utcnow() - timedelta(minutes=1)
    await db.commit()

    await capacidad_service.expirar_reservas(db)

    await db.refresh(pedido)
    assert pedido.estado == EstadoPedido.RECHAZADO
    assert "vencida" in pedido.motivo_rechazo.lower()

    entradas = (
        (
            await db.execute(
                select(PedidoHistorial)
                .where(PedidoHistorial.pedido_id == pedido.id)
                .order_by(PedidoHistorial.id)
            )
        )
        .scalars()
        .all()
    )
    ultima = entradas[-1]
    assert ultima.estado_anterior == EstadoPedido.APROBADO.value
    assert ultima.estado_nuevo == EstadoPedido.RECHAZADO.value
    assert ultima.usuario_id is None, "el autor debe ser el sistema, no una persona"


async def test_una_reserva_vigente_no_se_toca(
    client, db, catedra, usuario_catedra, template, auth_admin
):
    pedido = await _aprobado(client, db, catedra, usuario_catedra, template, auth_admin)

    resultado = await capacidad_service.expirar_reservas(db)

    assert resultado["afectados"] == 0
    await db.refresh(pedido)
    assert pedido.estado == EstadoPedido.APROBADO


async def test_un_pedido_ya_desplegado_no_expira(
    client, db, catedra, usuario_catedra, template, auth_admin
):
    """Con el servicio creado ya no hay reserva que vencer."""
    pedido = await _aprobado(client, db, catedra, usuario_catedra, template, auth_admin)
    await factories.crear_servicio(
        db,
        catedra_id=catedra.id,
        template_id=template.id,
        pedido_id=pedido.id,
        proxmox_vmid="190",
    )
    pedido.reserva_expira_at = datetime.utcnow() - timedelta(minutes=1)
    await db.commit()

    resultado = await capacidad_service.expirar_reservas(db)

    assert resultado["afectados"] == 0
    await db.refresh(pedido)
    assert pedido.estado == EstadoPedido.APROBADO


async def test_el_trabajo_es_ejecutable_a_mano_por_un_admin(client, auth_admin):
    r = await client.post("/admin/jobs/expirar_reservas", headers=auth_admin)

    assert r.status_code == 200, r.text
    assert r.json()["job"] == "expirar_reservas"


async def test_el_trabajo_no_es_ejecutable_por_una_catedra(client, auth_catedra):
    r = await client.post("/admin/jobs/expirar_reservas", headers=auth_catedra)

    assert r.status_code == 403, r.text
