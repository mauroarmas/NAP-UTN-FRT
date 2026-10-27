"""Revertir una aprobación antes del despliegue.

El defecto que originó la feature, reproducido el 2026-08-29: un pedido aprobado
compromete capacidad del clúster en el acto, y hasta acá la única forma de
soltarla era desplegarlo o esperar 24 h a que la reserva venciera sola. Mientras
tanto, el error de una cátedra bloqueaba a las demás.
"""

from datetime import timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.models.compromiso_capacidad import CompromisoCapacidad
from app.models.pedido import EstadoPedido
from app.models.servicio import EstadoServicio
from app.services import capacidad_service
from app.utils.clock import clock
from tests import factories
from tests.capacity_helpers import (
    aprobar_http,
    materializado,
    perfil_capacidad,
    seleccion,
)


@pytest.fixture(autouse=True)
def cluster(proxmox, perfil_capacidad):
    return proxmox


def _vigencia(dias_inicio=0, dias_fin=30):
    hoy = clock.now().astimezone(ZoneInfo("America/Argentina/Tucuman")).date()
    return {
        "tipo": "personalizado",
        "desde": (hoy + timedelta(days=dias_inicio)).isoformat(),
        "hasta": (hoy + timedelta(days=dias_fin)).isoformat(),
    }


async def _compromiso(db, pedido_id):
    return await db.scalar(
        select(CompromisoCapacidad).where(CompromisoCapacidad.pedido_id == pedido_id)
    )


async def _aprobado(client, db, catedra, usuario, template, auth_admin, **extra):
    pedido = await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario.id,
        template_id=template.id,
        estado=EstadoPedido.SOLICITADO,
    )
    r = await aprobar_http(client, pedido, template, auth_admin, **extra)
    assert r.status_code == 200, r.text
    await db.refresh(pedido)
    return pedido


def _revertir(client, pedido_id, headers, motivo="Aprobé el pedido equivocado", clave=None):
    return client.post(
        f"/pedidos/{pedido_id}/revertir-aprobacion",
        json={"motivo": motivo},
        headers=headers | {"Idempotency-Key": clave or f"rev-{uuid4()}"},
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
    ledger = await _compromiso(db, pedido.id)
    assert (ledger.vcpus_retenidos, ledger.ram_mb_retenida, ledger.disk_bytes_retenidos) == (0, 0, 0)
    assert ledger.expira_at is None
    assert ledger.estado == "liberado"


async def test_la_capacidad_libre_vuelve_exactamente_al_valor_previo(
    client, db, catedra, usuario_catedra, template, auth_admin
):
    """SC-002: ni más ni menos que lo que esa aprobación había comprometido."""
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
    """La justificación pertenece al registro de la aprobación que se deshace."""
    pedido = await _aprobado(
        client,
        db,
        catedra,
        usuario_catedra,
        template,
        auth_admin,
        justificacion_capacidad="urgencia de cursada",
    )

    r = await _revertir(client, pedido.id, auth_admin)
    assert r.status_code == 200, r.text

    await db.refresh(pedido)
    assert pedido.justificacion_capacidad == "urgencia de cursada"


# --- El motivo es obligatorio (FR-002, P2) ---------------------------------


@pytest.mark.parametrize(
    "cuerpo", [{}, {"motivo": ""}, {"motivo": "   "}], ids=["ausente", "vacio", "blanco"]
)
async def test_sin_motivo_no_se_revierte_ni_se_toca_nada(
    client, db, catedra, usuario_catedra, template, auth_admin, cuerpo
):
    """Un rechazo no puede dejar la operación a medias."""
    default_vcpus = template.default_vcpus
    pedido = await _aprobado(client, db, catedra, usuario_catedra, template, auth_admin)
    comprometida = await capacidad_service.panorama(db)

    r = await client.post(
        f"/pedidos/{pedido.id}/revertir-aprobacion",
        json=cuerpo,
        headers=auth_admin | {"Idempotency-Key": f"sin-motivo-{uuid4()}"},
    )

    assert r.status_code == 422, r.text
    await db.refresh(pedido)
    assert pedido.estado == EstadoPedido.APROBADO
    ledger = await _compromiso(db, pedido.id)
    assert ledger.vcpus_retenidos == default_vcpus
    assert (await capacidad_service.panorama(db))["libre"] == comprometida["libre"]


# --- Los conflictos con su código estructurado -------------------------


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
    assert r.json()["detail"]["codigo"] == "estado_incompatible"


@pytest.mark.parametrize(
    "estado",
    [EstadoPedido.EN_DESPLIEGUE, EstadoPedido.ACTIVO, EstadoPedido.ERROR],
)
async def test_con_el_despliegue_empezado_la_via_es_dar_de_baja_el_servicio(
    client, db, catedra, usuario_catedra, template, auth_admin, estado
):
    """En cuanto el aprovisionamiento tocó la infraestructura, no se libera como reserva sin reconciliar."""
    pedido = await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario_catedra.id,
        template_id=template.id,
        estado=estado,
    )

    r = await _revertir(client, pedido.id, auth_admin)

    assert r.status_code == 409, r.text
    assert r.json()["detail"]["codigo"] in {
        "estado_incompatible",
        "reserva_no_liberable",
        "reconciliacion_pendiente",
        "despliegue_en_curso",
    }


async def test_la_reserva_que_vencio_sola_da_su_propio_mensaje(
    client, db, catedra, usuario_catedra, template, auth_admin
):
    """Una reserva ya vencida y liberada por el sistema no vuelve a liberarse."""
    pedido = await _aprobado(client, db, catedra, usuario_catedra, template, auth_admin)
    ledger = await _compromiso(db, pedido.id)
    ledger.expira_at = clock.now() - timedelta(minutes=1)
    await db.commit()
    await capacidad_service.expirar_reservas(db)
    liberada = await capacidad_service.panorama(db)

    r = await _revertir(client, pedido.id, auth_admin)

    assert r.status_code == 409, r.text
    assert (await capacidad_service.panorama(db))["libre"] == liberada["libre"]


async def test_revertir_dos_veces_avisa_que_ya_estaba_revertido(
    client, db, catedra, usuario_catedra, template, auth_admin
):
    pedido = await _aprobado(client, db, catedra, usuario_catedra, template, auth_admin)
    assert (await _revertir(client, pedido.id, auth_admin)).status_code == 200
    ya_liberada = await capacidad_service.panorama(db)

    r = await _revertir(client, pedido.id, auth_admin, motivo="otra vez")

    assert r.status_code == 409, r.text
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
    client, db, proxmox, catedra, usuario_catedra, template, auth_admin, auth_catedra
):
    """Una renovación aprobada queda en ACTIVO sin reserva que liberar."""
    servicio, _ = await materializado(
        db, proxmox, catedra, usuario_catedra, template
    )
    servicio.estado = EstadoServicio.RUNNING
    await db.commit()

    r = await client.post(
        f"/servicios/{servicio.id}/renovar",
        json={"vigencia": _vigencia(dias_inicio=31, dias_fin=60)},
        headers=auth_catedra | {"Idempotency-Key": "renovar-rev-1"},
    )
    assert r.status_code == 201, r.text
    pedido_id = r.json()["pedido_id"]
    pedido_ren = await db.get(factories.Pedido, pedido_id)

    payload_ren = seleccion(
        template,
        desde=clock.now().astimezone(ZoneInfo("America/Argentina/Tucuman")).date() + timedelta(days=31),
        hasta=clock.now().astimezone(ZoneInfo("America/Argentina/Tucuman")).date() + timedelta(days=60),
    )
    payload_ren["asignacion"] = dict(servicio.asignacion_snapshot)
    assert (
        await aprobar_http(client, pedido_ren, template, auth_admin, payload=payload_ren)
    ).status_code == 200

    revertida = await _revertir(client, pedido_id, auth_admin, motivo="me confundí de servicio")
    assert revertida.status_code == 409, revertida.text
    await db.refresh(servicio)
    assert servicio.estado == EstadoServicio.RUNNING


# --- La otra puerta sigue cerrada (R1) -------------------------------------


async def test_patch_estado_sigue_rechazando_aprobado_a_rechazado(
    client, db, catedra, usuario_catedra, template, auth_admin
):
    """La reversión es una operación con nombre propio, no un cambio a mano."""
    pedido = await _aprobado(client, db, catedra, usuario_catedra, template, auth_admin)

    r = await client.patch(
        f"/pedidos/{pedido.id}/estado",
        json={"nuevo_estado": "rechazado", "motivo_rechazo": "por izquierda"},
        headers=auth_admin,
    )

    assert r.status_code == 405, r.text
    await db.refresh(pedido)
    assert pedido.estado == EstadoPedido.APROBADO
    ledger = await _compromiso(db, pedido.id)
    assert ledger.vcpus_retenidos == template.default_vcpus, "la reserva sigue intacta"
