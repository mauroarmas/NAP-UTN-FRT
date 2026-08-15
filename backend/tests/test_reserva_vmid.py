"""US1 — persistencia de la reserva de VMID (research R1).

Antes de este feature el VMID se pedía dentro del ``try`` y solo se guardaba al
crear el ``Servicio``, es decir *después* del éxito: si el despliegue fallaba, la
reserva se perdía y era imposible reutilizarla. Estas pruebas fijan el nuevo
comportamiento.
"""

from app.models.pedido import EstadoPedido
from tests import factories
from tests.fakes import ProxmoxFalla


async def test_despliegue_fallido_conserva_el_vmid_reservado(
    client, db, proxmox, catedra, usuario_catedra, template, auth_admin
):
    """research R1 — la reserva sobrevive al fallo del despliegue."""
    pedido = await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario_catedra.id,
        template_id=template.id,
        estado=EstadoPedido.APROBADO,
    )
    proxmox.next_vmid = 175
    proxmox.fallar_create = ProxmoxFalla("timeout contra el clúster")

    r = await client.post(f"/servicios/desplegar/{pedido.id}", headers=auth_admin)

    assert r.status_code == 502, r.text
    await db.refresh(pedido)
    assert pedido.estado == EstadoPedido.ERROR
    assert pedido.vmid_reservado == "175"


async def test_despliegue_exitoso_tambien_registra_la_reserva(
    client, db, proxmox, catedra, usuario_catedra, template, auth_admin
):
    pedido = await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario_catedra.id,
        template_id=template.id,
        estado=EstadoPedido.APROBADO,
    )
    proxmox.next_vmid = 180

    r = await client.post(f"/servicios/desplegar/{pedido.id}", headers=auth_admin)

    assert r.status_code == 200, r.text
    await db.refresh(pedido)
    assert pedido.vmid_reservado == "180"
    assert r.json()["proxmox_vmid"] == "180"
