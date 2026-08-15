"""US1 — resolución del VMID en el reintento (FR-004 y research R2).

Matriz de casos según contracts/api.md:
  sin reserva                          -> pedir VMID nuevo
  reserva libre                        -> reutilizar
  reserva ocupada, hostname propio     -> adoptar el contenedor existente
  reserva ocupada, hostname ajeno      -> pedir VMID nuevo
"""

from sqlalchemy import select

from app.models.pedido import EstadoPedido
from app.models.servicio import Servicio
from tests import factories
from tests.fakes import ocupar


async def _pedido_en_error(db, catedra, usuario_catedra, template, vmid_reservado=None):
    return await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario_catedra.id,
        template_id=template.id,
        estado=EstadoPedido.ERROR,
        vmid_reservado=vmid_reservado,
    )


async def test_reserva_libre_se_reutiliza(
    client, db, proxmox, catedra, usuario_catedra, template, auth_admin
):
    """US1 esc. 4 / FR-004 — el VMID reservado sigue libre, se reutiliza."""
    pedido = await _pedido_en_error(
        db, catedra, usuario_catedra, template, vmid_reservado="150"
    )
    proxmox.next_vmid = 200  # si pidiera uno nuevo, sería 200

    r = await client.post(f"/pedidos/{pedido.id}/reintentar", headers=auth_admin)

    assert r.status_code == 200, r.text
    assert r.json()["proxmox_vmid"] == "150"
    assert proxmox.llamadas_next_vmid == 0
    assert proxmox.creados[0]["vmid"] == 150


async def test_reserva_ocupada_por_tercero_pide_vmid_nuevo(
    client, db, proxmox, catedra, usuario_catedra, template, auth_admin
):
    """US1 esc. 5 — el VMID fue tomado por otro; se descarta la reserva."""
    pedido = await _pedido_en_error(
        db, catedra, usuario_catedra, template, vmid_reservado="150"
    )
    proxmox.recursos = [ocupar(150, "servidor-de-otra-catedra")]
    proxmox.next_vmid = 200

    r = await client.post(f"/pedidos/{pedido.id}/reintentar", headers=auth_admin)

    assert r.status_code == 200, r.text
    assert r.json()["proxmox_vmid"] == "200"
    assert proxmox.llamadas_next_vmid == 1


async def test_huerfano_propio_se_adopta_sin_crear_otro(
    client, db, proxmox, catedra, usuario_catedra, template, auth_admin
):
    """research R2 — fallo parcial previo: el contenedor existe, se adopta."""
    pedido = await _pedido_en_error(
        db, catedra, usuario_catedra, template, vmid_reservado="150"
    )
    hostname_propio = f"cat{catedra.id}-svc{pedido.id}"
    proxmox.recursos = [ocupar(150, hostname_propio)]

    r = await client.post(f"/pedidos/{pedido.id}/reintentar", headers=auth_admin)

    assert r.status_code == 200, r.text
    assert r.json()["proxmox_vmid"] == "150"
    # Lo esencial: NO se creó un segundo contenedor
    assert proxmox.creados == []
    assert proxmox.llamadas_next_vmid == 0

    servicios = (
        (await db.execute(select(Servicio).where(Servicio.pedido_id == pedido.id)))
        .scalars()
        .all()
    )
    assert len(servicios) == 1
    assert servicios[0].proxmox_vmid == "150"


async def test_sin_reserva_previa_pide_vmid_nuevo(
    client, db, proxmox, catedra, usuario_catedra, template, auth_admin
):
    """Sin reserva (fallo anterior a la persistencia): se pide uno nuevo."""
    pedido = await _pedido_en_error(db, catedra, usuario_catedra, template)
    proxmox.next_vmid = 300

    r = await client.post(f"/pedidos/{pedido.id}/reintentar", headers=auth_admin)

    assert r.status_code == 200, r.text
    assert r.json()["proxmox_vmid"] == "300"
    assert proxmox.llamadas_next_vmid == 1
