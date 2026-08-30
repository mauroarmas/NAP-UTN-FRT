"""Las tres formas de llegar a rechazado, distinguibles en el historial (US3).

Un rechazo original, una reversión de aprobación y un vencimiento de reserva
terminan los tres en el mismo estado. Sin distinguirlos, el historial no permite
reconstruir si hubo capacidad comprometida y por cuánto tiempo — que es
exactamente lo que el Principio V exige poder responder.

La distinción no necesita campos ni estados nuevos: sale del par (estado
anterior, autor), que ya se registra en cada entrada (R4).
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.pedido import EstadoPedido, PedidoHistorial
from app.services import capacidad_service
from tests import factories

NODO = [
    {
        "node": "pve1",
        "status": "online",
        "cpu": 0.1,
        "maxcpu": 16,
        "maxmem": 32 * 1024**3,
        "maxdisk": 200 * 1024**3,
    }
]

MOTIVO = "Me confundí de cátedra al aprobar"


@pytest.fixture(autouse=True)
def cluster(proxmox):
    proxmox.nodos = NODO
    return proxmox


async def _pedido(db, catedra, usuario, template):
    return await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario.id,
        template_id=template.id,
        estado=EstadoPedido.SOLICITADO,
    )


async def _entradas(db, pedido_id) -> list[PedidoHistorial]:
    return list(
        (
            await db.execute(
                select(PedidoHistorial)
                .where(PedidoHistorial.pedido_id == pedido_id)
                .order_by(PedidoHistorial.id)
            )
        ).scalars()
    )


async def test_el_historial_distingue_las_tres_formas_de_llegar_a_rechazado(
    client, db, catedra, usuario_catedra, template, auth_admin
):
    """FR-009, R4, SC-004 — los tres casos producidos sobre pedidos distintos.

    El **estado anterior** separa el rechazo original de los otros dos; el
    **autor** separa la reversión del vencimiento.
    """
    rechazado = await _pedido(db, catedra, usuario_catedra, template)
    revertido = await _pedido(db, catedra, usuario_catedra, template)
    vencido = await _pedido(db, catedra, usuario_catedra, template)

    # 1. Rechazado de entrada, sin pasar nunca por aprobado.
    assert (
        await client.post(
            f"/pedidos/{rechazado.id}/rechazar",
            json={"motivo": "el template no corresponde a la materia"},
            headers=auth_admin,
        )
    ).status_code == 200

    # 2. Aprobado y después revertido por una persona.
    await client.post(f"/pedidos/{revertido.id}/aprobar", json={}, headers=auth_admin)
    assert (
        await client.post(
            f"/pedidos/{revertido.id}/revertir-aprobacion",
            json={"motivo": MOTIVO},
            headers=auth_admin,
        )
    ).status_code == 200

    # 3. Aprobado y liberado solo por el sistema al vencer la reserva.
    await client.post(f"/pedidos/{vencido.id}/aprobar", json={}, headers=auth_admin)
    await db.refresh(vencido)
    vencido.reserva_expira_at = datetime.utcnow() - timedelta(minutes=1)
    await db.commit()
    await capacidad_service.expirar_reservas(db)

    ultima_rechazo = (await _entradas(db, rechazado.id))[-1]
    ultima_reversion = (await _entradas(db, revertido.id))[-1]
    ultima_vencimiento = (await _entradas(db, vencido.id))[-1]

    # Los tres llegan al mismo estado…
    assert {
        ultima_rechazo.estado_nuevo,
        ultima_reversion.estado_nuevo,
        ultima_vencimiento.estado_nuevo,
    } == {EstadoPedido.RECHAZADO.value}

    # …y aun así los tres se distinguen sin ambigüedad.
    assert ultima_rechazo.estado_anterior == EstadoPedido.SOLICITADO.value
    assert ultima_rechazo.usuario_id is not None

    assert ultima_reversion.estado_anterior == EstadoPedido.APROBADO.value
    assert ultima_reversion.usuario_id is not None, "la revirtió una persona"

    assert ultima_vencimiento.estado_anterior == EstadoPedido.APROBADO.value
    assert ultima_vencimiento.usuario_id is None, "lo hizo el sistema, no alguien"


async def test_la_entrada_de_la_aprobacion_original_sobrevive_a_la_reversion(
    client, db, catedra, usuario_catedra, template, auth_admin, admin
):
    """FR-008, H1, H3, I4.

    Dos cosas en una: que la reversión **agregue** una entrada en lugar de
    reescribir la de la aprobación —leídas en orden, las dos cuentan la historia
    completa: se aprobó, y después se deshizo—, y que el motivo que escribió el
    administrador viaje en el comentario de la entrada nueva. Sin el motivo, el
    historial dice que alguien deshizo algo pero no por qué, y la auditoría del
    Principio V queda a medias.
    """
    pedido = await _pedido(db, catedra, usuario_catedra, template)
    await client.post(f"/pedidos/{pedido.id}/aprobar", json={}, headers=auth_admin)
    assert (
        await client.post(
            f"/pedidos/{pedido.id}/revertir-aprobacion",
            json={"motivo": MOTIVO},
            headers=auth_admin,
        )
    ).status_code == 200

    entradas = await _entradas(db, pedido.id)
    aprobacion = [
        e for e in entradas if e.estado_nuevo == EstadoPedido.APROBADO.value
    ]
    reversion = [
        e
        for e in entradas
        if e.estado_anterior == EstadoPedido.APROBADO.value
        and e.estado_nuevo == EstadoPedido.RECHAZADO.value
    ]

    assert len(aprobacion) == 1, "la aprobación no se borra ni se sobrescribe"
    assert len(reversion) == 1
    assert entradas.index(aprobacion[0]) < entradas.index(reversion[0]), (
        "leídas en orden: se aprobó, y después se deshizo"
    )
    assert MOTIVO in reversion[0].comentario, (
        "el motivo que escribió el administrador tiene que quedar en el historial"
    )
    assert reversion[0].usuario_id == admin.id, (
        "el autor es la persona que revirtió, nunca el sistema, aunque la "
        "operación se parezca al vencimiento automático (H2)"
    )


async def test_el_detalle_del_pedido_expone_el_historial_completo(
    client, db, catedra, usuario_catedra, template, auth_admin, auth_catedra
):
    """La distinción tiene que llegar a quien la mira, no quedarse en la base."""
    pedido = await _pedido(db, catedra, usuario_catedra, template)
    await client.post(f"/pedidos/{pedido.id}/aprobar", json={}, headers=auth_admin)
    await client.post(
        f"/pedidos/{pedido.id}/revertir-aprobacion",
        json={"motivo": MOTIVO},
        headers=auth_admin,
    )

    r = await client.get(f"/pedidos/{pedido.id}", headers=auth_catedra)

    historial = r.json()["historial"]
    ultima = historial[-1]
    assert ultima["estado_anterior"] == EstadoPedido.APROBADO.value
    assert ultima["estado_nuevo"] == EstadoPedido.RECHAZADO.value
    assert ultima["usuario_id"] is not None
    assert MOTIVO in ultima["comentario"]
