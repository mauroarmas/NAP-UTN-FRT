"""US1 — máquina de estados del reintento de despliegue."""

import pytest
from sqlalchemy import select

from app.models.pedido import EstadoPedido, Pedido, PedidoHistorial
from tests import factories
from tests.fakes import ProxmoxFalla


async def _pedido_en_error(db, catedra, usuario_catedra, template, **kwargs):
    return await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario_catedra.id,
        template_id=template.id,
        estado=EstadoPedido.ERROR,
        **kwargs,
    )


async def test_reintento_exitoso_deja_el_pedido_activo(
    client, db, proxmox, catedra, usuario_catedra, template, auth_admin
):
    """US1 esc. 1 — el reintento vuelve a desplegar y el pedido queda ACTIVO."""
    pedido = await _pedido_en_error(db, catedra, usuario_catedra, template)

    r = await client.post(f"/pedidos/{pedido.id}/reintentar", headers=auth_admin)

    assert r.status_code == 200, r.text
    assert r.json()["proxmox_vmid"] is not None
    await db.refresh(pedido)
    assert pedido.estado == EstadoPedido.ACTIVO
    assert len(proxmox.creados) == 1


async def test_reintento_fallido_conserva_historial_anterior(
    client, db, proxmox, catedra, usuario_catedra, template, auth_admin
):
    """US1 esc. 2 / FR-005 — un reintento que falla agrega historial, no lo pisa."""
    pedido = await _pedido_en_error(db, catedra, usuario_catedra, template)
    # Historial preexistente del intento original
    db.add(
        PedidoHistorial(
            pedido_id=pedido.id,
            estado_anterior="en_despliegue",
            estado_nuevo="error",
            comentario="Error Proxmox: fallo original",
            usuario_id=usuario_catedra.id,
        )
    )
    await db.commit()

    proxmox.fallar_create = ProxmoxFalla("el clúster sigue caído")

    r = await client.post(f"/pedidos/{pedido.id}/reintentar", headers=auth_admin)

    assert r.status_code == 502, r.text
    await db.refresh(pedido)
    assert pedido.estado == EstadoPedido.ERROR

    filas = (
        (
            await db.execute(
                select(PedidoHistorial)
                .where(PedidoHistorial.pedido_id == pedido.id)
                .order_by(PedidoHistorial.created_at)
            )
        )
        .scalars()
        .all()
    )
    # El original + (error→en_despliegue) + (en_despliegue→error) del reintento
    assert len(filas) >= 3
    assert any("fallo original" in (f.comentario or "") for f in filas)
    assert any("sigue caído" in (f.comentario or "") for f in filas)


@pytest.mark.parametrize(
    "estado", [EstadoPedido.ACTIVO, EstadoPedido.RECHAZADO, EstadoPedido.APROBADO]
)
async def test_reintento_sobre_estado_invalido_responde_409(
    client, db, proxmox, catedra, usuario_catedra, template, auth_admin, estado
):
    """US1 esc. 3 / FR-002 — solo se reintenta desde ERROR."""
    pedido = await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario_catedra.id,
        template_id=template.id,
        estado=estado,
    )

    r = await client.post(f"/pedidos/{pedido.id}/reintentar", headers=auth_admin)

    assert r.status_code == 409, r.text
    assert estado.value in r.json()["detail"]
    assert proxmox.creados == []


async def test_reintento_de_pedido_inexistente_responde_404(client, proxmox, auth_admin):
    r = await client.post("/pedidos/9999/reintentar", headers=auth_admin)
    assert r.status_code == 404


async def test_varios_reintentos_registran_cada_intento(
    client, db, proxmox, catedra, usuario_catedra, template, auth_admin
):
    """US1 esc. 6 — cada intento queda como entrada distinta y ordenada."""
    pedido = await _pedido_en_error(db, catedra, usuario_catedra, template)

    proxmox.fallar_create = ProxmoxFalla("primer reintento falla")
    r1 = await client.post(f"/pedidos/{pedido.id}/reintentar", headers=auth_admin)
    assert r1.status_code == 502

    proxmox.fallar_create = None
    r2 = await client.post(f"/pedidos/{pedido.id}/reintentar", headers=auth_admin)
    assert r2.status_code == 200, r2.text

    await db.refresh(pedido)
    assert pedido.estado == EstadoPedido.ACTIVO

    filas = (
        (
            await db.execute(
                select(PedidoHistorial)
                .where(PedidoHistorial.pedido_id == pedido.id)
                .order_by(PedidoHistorial.created_at)
            )
        )
        .scalars()
        .all()
    )
    transiciones = [(f.estado_anterior, f.estado_nuevo) for f in filas]
    assert ("error", "en_despliegue") in transiciones
    assert ("en_despliegue", "error") in transiciones
    assert ("en_despliegue", "activo") in transiciones
