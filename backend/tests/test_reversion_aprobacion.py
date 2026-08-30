"""Revertir una aprobación antes del despliegue.

El defecto que originó la feature, reproducido el 2026-08-29: un pedido aprobado
compromete capacidad del clúster en el acto, y hasta acá la única forma de
soltarla era desplegarlo o esperar 24 h a que la reserva venciera sola. Mientras
tanto, el error de una cátedra bloqueaba a las demás.
"""

from datetime import datetime, timedelta

import pytest

from app.models.pedido import EstadoPedido, TipoPedido
from app.models.servicio import EstadoServicio
from app.services import capacidad_service
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


def _revertir(client, pedido_id, headers, motivo="Aprobé el pedido equivocado"):
    return client.post(
        f"/pedidos/{pedido_id}/revertir-aprobacion",
        json={"motivo": motivo},
        headers=headers,
    )


# --- Camino feliz (FR-001, FR-003, SC-002) ---------------------------------


async def test_revertir_deja_el_pedido_rechazado_y_la_reserva_en_cero(
    client, db, catedra, usuario_catedra, template, auth_admin
):
    pedido = await _aprobado(client, db, catedra, usuario_catedra, template, auth_admin)

    r = await _revertir(client, pedido.id, auth_admin)

    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["estado"] == EstadoPedido.RECHAZADO.value
    assert (cuerpo["reserva_vcpus"], cuerpo["reserva_ram_mb"], cuerpo["reserva_disk_gb"]) == (0, 0, 0)
    assert cuerpo["reserva_expira_at"] is None


async def test_la_capacidad_libre_vuelve_exactamente_al_valor_previo(
    client, db, catedra, usuario_catedra, template, auth_admin
):
    """SC-002: ni más ni menos que lo que esa aprobación había comprometido.

    Es la medida que importa: si volviera de más, el sistema aprobaría sobre
    recursos inexistentes; si volviera de menos, quedaría capacidad fantasma.
    """
    antes = await capacidad_service.panorama(db)

    pedido = await _aprobado(client, db, catedra, usuario_catedra, template, auth_admin)
    comprometida = await capacidad_service.panorama(db)
    assert comprometida["libre"]["vcpus"] < antes["libre"]["vcpus"]

    r = await _revertir(client, pedido.id, auth_admin)
    assert r.status_code == 200, r.text

    despues = await capacidad_service.panorama(db)
    assert despues["libre"] == antes["libre"]
    assert despues["reservado"] == antes["reservado"]


async def test_la_respuesta_dice_cuanta_capacidad_volvio(
    client, db, catedra, usuario_catedra, template, auth_admin
):
    """Para que la interfaz lo muestre sin tener que volver a consultar."""
    pedido = await _aprobado(client, db, catedra, usuario_catedra, template, auth_admin)

    r = await _revertir(client, pedido.id, auth_admin)

    assert r.json()["capacidad_liberada"] == {
        "vcpus": template.default_vcpus,
        "ram_mb": template.default_ram_mb,
        "storage_gb": template.default_disk_gb,
    }


async def test_revertir_no_borra_la_justificacion_de_la_aprobacion(
    client, db, catedra, usuario_catedra, template, auth_admin
):
    """La justificación pertenece al registro de la aprobación que se deshace.

    Borrarla perdería la mitad de la historia: por qué alguien decidió
    comprometer de más. Lo que se deshace es el compromiso, no el registro.
    """
    pedido = await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario_catedra.id,
        template_id=template.id,
        estado=EstadoPedido.SOLICITADO,
    )
    await client.post(
        f"/pedidos/{pedido.id}/aprobar",
        json={"justificacion_capacidad": "urgencia de cursada"},
        headers=auth_admin,
    )

    r = await _revertir(client, pedido.id, auth_admin)

    assert r.json()["justificacion_capacidad"] == "urgencia de cursada"


# --- El motivo es obligatorio (FR-002, P2) ---------------------------------


@pytest.mark.parametrize(
    "cuerpo", [{}, {"motivo": ""}, {"motivo": "   "}], ids=["ausente", "vacio", "blanco"]
)
async def test_sin_motivo_no_se_revierte_ni_se_toca_nada(
    client, db, catedra, usuario_catedra, template, auth_admin, cuerpo
):
    """Un rechazo no puede dejar la operación a medias.

    Se comprueban las dos mitades: que devuelve 400 y que el pedido sigue
    aprobado con su capacidad comprometida.
    """
    pedido = await _aprobado(client, db, catedra, usuario_catedra, template, auth_admin)
    comprometida = await capacidad_service.panorama(db)

    r = await client.post(
        f"/pedidos/{pedido.id}/revertir-aprobacion", json=cuerpo, headers=auth_admin
    )

    assert r.status_code == 400, r.text
    await db.refresh(pedido)
    assert pedido.estado == EstadoPedido.APROBADO
    assert pedido.reserva_vcpus == template.default_vcpus
    assert (await capacidad_service.panorama(db))["libre"] == comprometida["libre"]


# --- Los cuatro conflictos, cada uno con su nombre -------------------------


async def test_un_pedido_nunca_aprobado_no_tiene_nada_que_deshacer(
    client, db, catedra, usuario_catedra, template, auth_admin
):
    pedido = await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario_catedra.id,
        template_id=template.id,
        estado=EstadoPedido.SOLICITADO,
    )

    r = await _revertir(client, pedido.id, auth_admin)

    assert r.status_code == 409, r.text
    assert r.json()["detail"]["codigo"] == "pedido_no_aprobado"
    assert r.json()["detail"]["estado_actual"] == EstadoPedido.SOLICITADO.value


@pytest.mark.parametrize(
    "estado",
    [EstadoPedido.EN_DESPLIEGUE, EstadoPedido.ACTIVO, EstadoPedido.ERROR],
)
async def test_con_el_despliegue_empezado_la_via_es_dar_de_baja_el_servicio(
    client, db, catedra, usuario_catedra, template, auth_admin, estado
):
    """En cuanto el aprovisionamiento tocó la infraestructura, la vuelta atrás
    deja de ser administrativa y pasa a ser una baja de servicio (R5)."""
    pedido = await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario_catedra.id,
        template_id=template.id,
        estado=estado,
    )

    r = await _revertir(client, pedido.id, auth_admin)

    assert r.status_code == 409, r.text
    assert r.json()["detail"]["codigo"] == "despliegue_en_curso"
    assert r.json()["detail"]["estado_actual"] == estado.value


async def test_la_reserva_que_vencio_sola_da_su_propio_mensaje(
    client, db, catedra, usuario_catedra, template, auth_admin
):
    """FR-014: no un genérico "transición inválida".

    Ante algo que el sistema hizo por su cuenta, un mensaje técnico se lee como
    una falla del portal.
    """
    pedido = await _aprobado(client, db, catedra, usuario_catedra, template, auth_admin)
    pedido.reserva_expira_at = datetime.utcnow() - timedelta(minutes=1)
    await db.commit()
    await capacidad_service.expirar_reservas(db)
    liberada = await capacidad_service.panorama(db)

    r = await _revertir(client, pedido.id, auth_admin)

    assert r.status_code == 409, r.text
    assert r.json()["detail"]["codigo"] == "reserva_ya_vencida"
    # Y no se libera por segunda vez.
    assert (await capacidad_service.panorama(db))["libre"] == liberada["libre"]


async def test_revertir_dos_veces_avisa_que_ya_estaba_revertido(
    client, db, catedra, usuario_catedra, template, auth_admin
):
    pedido = await _aprobado(client, db, catedra, usuario_catedra, template, auth_admin)
    assert (await _revertir(client, pedido.id, auth_admin)).status_code == 200
    ya_liberada = await capacidad_service.panorama(db)

    r = await _revertir(client, pedido.id, auth_admin, motivo="otra vez")

    assert r.status_code == 409, r.text
    assert r.json()["detail"]["codigo"] == "ya_revertido"
    assert (await capacidad_service.panorama(db))["libre"] == ya_liberada["libre"]


async def test_una_catedra_no_puede_revertir_ni_su_propio_pedido(
    client, db, catedra, usuario_catedra, template, auth_admin, auth_catedra
):
    """FR-012: aprobar y deshacer son la misma decisión, y es del administrador."""
    pedido = await _aprobado(client, db, catedra, usuario_catedra, template, auth_admin)

    r = await _revertir(client, pedido.id, auth_catedra)

    assert r.status_code == 403, r.text
    await db.refresh(pedido)
    assert pedido.estado == EstadoPedido.APROBADO


async def test_un_pedido_inexistente_da_404(client, auth_admin):
    r = await _revertir(client, 9999, auth_admin)

    assert r.status_code == 404, r.text


# --- Renovaciones (FR-013, R7, P5) -----------------------------------------


async def test_revertir_una_renovacion_no_toca_el_servicio_renovado(
    client, db, catedra, usuario_catedra, template, auth_admin, auth_catedra
):
    """El servicio conserva su fecha de fin y sigue corriendo.

    Sale gratis por construcción: una renovación aprobada no reserva capacidad
    y `vence_at` no se mueve hasta que la renovación se **ejecuta**. Revertir
    antes de ejecutarla deja al servicio exactamente como estaba.
    """
    servicio = await factories.crear_servicio(
        db, catedra_id=catedra.id, template_id=template.id, proxmox_vmid="710"
    )
    servicio.vence_at = datetime.utcnow() + timedelta(days=30)
    await db.commit()
    vence_original = servicio.vence_at

    r = await client.post(f"/servicios/{servicio.id}/renovar", headers=auth_catedra)
    assert r.status_code == 201, r.text
    pedido_id = r.json()["pedido_id"]
    assert (
        await client.post(f"/pedidos/{pedido_id}/aprobar", json={}, headers=auth_admin)
    ).status_code == 200

    revertida = await _revertir(client, pedido_id, auth_admin, motivo="me confundí de servicio")

    assert revertida.status_code == 200, revertida.text
    assert revertida.json()["capacidad_liberada"] == {
        "vcpus": 0,
        "ram_mb": 0,
        "storage_gb": 0,
    }, "una renovación no reservaba nada, así que no libera nada"
    await db.refresh(servicio)
    assert servicio.vence_at == vence_original
    assert servicio.estado == EstadoServicio.RUNNING


# --- La otra puerta sigue cerrada (R1) -------------------------------------


async def test_patch_estado_sigue_rechazando_aprobado_a_rechazado(
    client, db, catedra, usuario_catedra, template, auth_admin
):
    """La reversión es una operación con nombre propio, no un cambio a mano.

    Habilitar la transición en `PATCH /estado` sería el atajo obvio y el error:
    movería el estado **sin liberar la reserva**, que es exactamente la
    capacidad huérfana que esa restricción previene. Si algún día esta prueba
    empieza a fallar, es que se abrió esa puerta.
    """
    pedido = await _aprobado(client, db, catedra, usuario_catedra, template, auth_admin)

    r = await client.patch(
        f"/pedidos/{pedido.id}/estado",
        json={"nuevo_estado": "rechazado", "motivo_rechazo": "por izquierda"},
        headers=auth_admin,
    )

    assert r.status_code == 409, r.text
    await db.refresh(pedido)
    assert pedido.estado == EstadoPedido.APROBADO
    assert pedido.reserva_vcpus == template.default_vcpus, "la reserva sigue intacta"
