"""US2 — baja lógica de pedidos (FR-013 a FR-015)."""

from sqlalchemy import select

from app.models.pedido import EstadoPedido, Pedido
from tests import factories


async def test_pedido_sin_servicio_se_da_de_baja(
    client, db, proxmox, catedra, usuario_catedra, template, auth_admin
):
    """US2 esc. 6 / FR-013 — un pedido rechazado se da de baja sin tocar Proxmox."""
    pedido = await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario_catedra.id,
        template_id=template.id,
        estado=EstadoPedido.RECHAZADO,
    )

    r = await client.delete(f"/pedidos/{pedido.id}", headers=auth_admin)

    assert r.status_code == 200, r.text
    assert r.json()["deleted_at"] is not None
    assert proxmox.eliminados == []

    fila = (
        await db.execute(select(Pedido).where(Pedido.id == pedido.id))
    ).scalar_one()
    assert fila.deleted_at is not None


async def test_pedido_con_servicio_vigente_responde_409(
    client, db, proxmox, catedra, usuario_catedra, template, auth_admin
):
    """US2 esc. 7 / FR-014 — primero hay que liberar el recurso real."""
    pedido = await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario_catedra.id,
        template_id=template.id,
        estado=EstadoPedido.ACTIVO,
    )
    servicio = await factories.crear_servicio(
        db, catedra_id=catedra.id, template_id=template.id, pedido_id=pedido.id
    )

    r = await client.delete(f"/pedidos/{pedido.id}", headers=auth_admin)

    assert r.status_code == 409, r.text
    assert str(servicio.id) in r.json()["detail"]
    await db.refresh(pedido)
    assert pedido.deleted_at is None


async def test_pedido_se_da_de_baja_tras_dar_de_baja_su_servicio(
    client, db, proxmox, catedra, usuario_catedra, template, auth_admin
):
    """El orden operativo esperado: primero el servicio, después el pedido."""
    pedido = await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario_catedra.id,
        template_id=template.id,
        estado=EstadoPedido.ACTIVO,
    )
    servicio = await factories.crear_servicio(
        db,
        catedra_id=catedra.id,
        template_id=template.id,
        pedido_id=pedido.id,
        proxmox_vmid="130",
    )

    assert (
        await client.delete(f"/servicios/{servicio.id}", headers=auth_admin)
    ).status_code == 200
    r = await client.delete(f"/pedidos/{pedido.id}", headers=auth_admin)

    assert r.status_code == 200, r.text


async def test_usuario_de_catedra_no_puede_dar_de_baja(
    client, db, proxmox, catedra, usuario_catedra, template, auth_catedra
):
    """FR-015 — la baja es administrativa."""
    pedido = await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario_catedra.id,
        template_id=template.id,
        estado=EstadoPedido.RECHAZADO,
    )

    r = await client.delete(f"/pedidos/{pedido.id}", headers=auth_catedra)

    assert r.status_code == 403, r.text
    await db.refresh(pedido)
    assert pedido.deleted_at is None


async def test_pedido_dado_de_baja_sale_de_listados(
    client, db, proxmox, catedra, usuario_catedra, template, auth_admin
):
    """FR-009 — fuera de los listados y 404 en el detalle."""
    pedido = await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario_catedra.id,
        template_id=template.id,
        estado=EstadoPedido.RECHAZADO,
    )
    await client.delete(f"/pedidos/{pedido.id}", headers=auth_admin)

    listado = await client.get("/pedidos/", headers=auth_admin)
    assert listado.status_code == 200
    assert all(p["id"] != pedido.id for p in listado.json())

    detalle = await client.get(f"/pedidos/{pedido.id}", headers=auth_admin)
    assert detalle.status_code == 404


async def test_doble_baja_de_pedido_es_idempotente(
    client, db, proxmox, catedra, usuario_catedra, template, auth_admin
):
    pedido = await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario_catedra.id,
        template_id=template.id,
        estado=EstadoPedido.RECHAZADO,
    )

    assert (
        await client.delete(f"/pedidos/{pedido.id}", headers=auth_admin)
    ).status_code == 200
    r2 = await client.delete(f"/pedidos/{pedido.id}", headers=auth_admin)

    assert r2.status_code == 200, r2.text
    assert "ya estaba dado de baja" in r2.json()["message"]


async def test_pedido_dado_de_baja_no_se_puede_reintentar(
    client, db, proxmox, catedra, usuario_catedra, template, auth_admin
):
    """El reintento de US1 tampoco debe alcanzar registros dados de baja."""
    pedido = await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario_catedra.id,
        template_id=template.id,
        estado=EstadoPedido.ERROR,
    )
    await client.delete(f"/pedidos/{pedido.id}", headers=auth_admin)

    r = await client.post(f"/pedidos/{pedido.id}/reintentar", headers=auth_admin)

    assert r.status_code == 404
    assert proxmox.creados == []
