"""Lo que ve la cátedra cuando su aprobación se deshace (US2).

Un pedido que estaba aprobado y deja de estarlo en silencio es indistinguible
de una falla del portal. La cátedra pierde la confianza en los estados que el
sistema le muestra, que es justamente lo que la máquina de estados existe para
sostener.
"""

import pytest

from app.models.pedido import EstadoPedido
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

MOTIVO = "Aprobé el template grande por error; la cátedra había pedido el chico"


@pytest.fixture(autouse=True)
def cluster(proxmox):
    proxmox.nodos = NODO
    return proxmox


async def _aprobado_y_revertido(client, db, catedra, usuario, template, auth_admin):
    pedido = await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario.id,
        template_id=template.id,
        estado=EstadoPedido.SOLICITADO,
    )
    assert (
        await client.post(f"/pedidos/{pedido.id}/aprobar", json={}, headers=auth_admin)
    ).status_code == 200
    r = await client.post(
        f"/pedidos/{pedido.id}/revertir-aprobacion",
        json={"motivo": MOTIVO},
        headers=auth_admin,
    )
    assert r.status_code == 200, r.text
    return pedido


async def test_la_catedra_ve_el_pedido_revertido_con_el_motivo_que_escribio_el_admin(
    client, db, catedra, usuario_catedra, template, auth_admin, auth_catedra
):
    """FR-010. El motivo tiene que ser el que escribió la persona, no un texto
    genérico: sin él, la cátedra no puede saber si rehacer el pedido tiene
    sentido o si hay algo que corregir de su lado."""
    pedido = await _aprobado_y_revertido(
        client, db, catedra, usuario_catedra, template, auth_admin
    )

    r = await client.get(f"/pedidos/{pedido.id}", headers=auth_catedra)

    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["estado"] == EstadoPedido.RECHAZADO.value
    assert MOTIVO in cuerpo["motivo_rechazo"]
    assert "revertida" in cuerpo["motivo_rechazo"].lower(), (
        "el texto debe nombrar la reversión: leído como 'rechazado' a secas, "
        "el pedido parece haber sido evaluado y desestimado"
    )


async def test_la_catedra_ve_la_reversion_en_su_listado(
    client, db, catedra, usuario_catedra, template, auth_admin, auth_catedra
):
    """El cambio llega por el mismo canal por el que ya sigue sus pedidos."""
    pedido = await _aprobado_y_revertido(
        client, db, catedra, usuario_catedra, template, auth_admin
    )

    r = await client.get("/pedidos/", headers=auth_catedra)

    assert r.status_code == 200, r.text
    fila = next(p for p in r.json() if p["id"] == pedido.id)
    assert fila["estado"] == EstadoPedido.RECHAZADO.value
    assert MOTIVO in fila["motivo_rechazo"]


async def test_la_catedra_puede_volver_a_pedir_lo_mismo(
    client, db, catedra, usuario_catedra, template, auth_admin, auth_catedra
):
    """FR-011, P6: la reversión no es una sanción.

    Lo más común es que el pedido se rehaga cuando haya capacidad. Bloquearlo
    castigaría a quien no cometió el error.
    """
    await _aprobado_y_revertido(client, db, catedra, usuario_catedra, template, auth_admin)

    nuevo = await client.post(
        "/pedidos/", json={"template_id": template.id}, headers=auth_catedra
    )

    assert nuevo.status_code == 201, nuevo.text
    assert nuevo.json()["estado"] == EstadoPedido.SOLICITADO.value

    # Y aparece en la bandeja del administrador, como cualquier otro.
    bandeja = await client.get("/pedidos/?estado=solicitado", headers=auth_admin)
    assert nuevo.json()["id"] in [p["id"] for p in bandeja.json()]


async def test_una_catedra_ajena_sigue_sin_ver_el_pedido_revertido(
    client, db, catedra, usuario_catedra, template, auth_admin
):
    """Revertir no ensancha lo que cada cátedra puede ver."""
    pedido = await _aprobado_y_revertido(
        client, db, catedra, usuario_catedra, template, auth_admin
    )
    otro = await factories.crear_usuario(db, "ajeno")
    await factories.crear_catedra(db, nombre="Otra", titular_id=otro.id)
    from app.utils.security import create_access_token

    headers = {
        "Authorization": "Bearer "
        + create_access_token({"sub": otro.username, "rol": otro.rol.value})
    }

    r = await client.get(f"/pedidos/{pedido.id}", headers=headers)

    assert r.status_code == 403, r.text
