"""US1 — control de acceso del reintento (FR-006)."""

from app.models.pedido import EstadoPedido
from tests import factories


async def test_usuario_de_catedra_no_puede_reintentar(
    client, db, proxmox, catedra, usuario_catedra, template, auth_catedra
):
    """FR-006 — el reintento es una transición administrativa."""
    pedido = await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario_catedra.id,
        template_id=template.id,
        estado=EstadoPedido.ERROR,
    )

    r = await client.post(f"/pedidos/{pedido.id}/reintentar", headers=auth_catedra)

    assert r.status_code == 403, r.text
    assert proxmox.creados == []
    await db.refresh(pedido)
    assert pedido.estado == EstadoPedido.ERROR


async def test_sin_token_no_puede_reintentar(
    client, db, proxmox, catedra, usuario_catedra, template
):
    pedido = await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario_catedra.id,
        template_id=template.id,
        estado=EstadoPedido.ERROR,
    )

    r = await client.post(f"/pedidos/{pedido.id}/reintentar")

    assert r.status_code == 401
    assert proxmox.creados == []
