"""Expiración de reservas: la capacidad comprometida tampoco queda huérfana.

Un pedido aprobado que nunca se despliega retendría capacidad para siempre. Es
la misma clase de fuga silenciosa que un contenedor sin registro, solo que sin
contenedor que encontrar.
"""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.models.compromiso_capacidad import CompromisoCapacidad
from app.models.pedido import EstadoPedido, PedidoHistorial
from app.services import capacidad_service
from app.services.admision_service import expiracion_reserva
from app.services.vigencia_service import resolver_fechas
from app.utils.clock import clock, db_utc
from tests import factories
from tests.capacity_helpers import (
    aprobar_http,
    perfil_capacidad,
    preparar_pedido,
    seleccion,
)


@pytest.fixture(autouse=True)
def cluster(proxmox, perfil_capacidad):
    return proxmox


async def _aprobado(client, db, catedra, usuario, template, auth_admin):
    pedido = await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario.id,
        template_id=template.id,
        estado=EstadoPedido.SOLICITADO,
    )
    r = await aprobar_http(client, pedido, template, auth_admin)
    assert r.status_code == 200, r.text
    await db.refresh(pedido)
    return pedido


async def _compromiso(db, pedido_id):
    return await db.scalar(
        select(CompromisoCapacidad).where(CompromisoCapacidad.pedido_id == pedido_id)
    )


async def test_aprobar_fija_un_vencimiento_a_la_reserva(
    client, db, catedra, usuario_catedra, template, auth_admin
):
    pedido = await _aprobado(client, db, catedra, usuario_catedra, template, auth_admin)
    ledger = await _compromiso(db, pedido.id)

    assert ledger is not None
    assert ledger.expira_at is not None
    assert ledger.vcpus_retenidos == template.default_vcpus


async def test_la_reserva_vencida_libera_la_capacidad(
    client, db, catedra, usuario_catedra, template, auth_admin
):
    pedido = await _aprobado(client, db, catedra, usuario_catedra, template, auth_admin)

    con_reserva = await capacidad_service.panorama(db)
    assert con_reserva["reservado"]["vcpus"] == template.default_vcpus

    ledger = await _compromiso(db, pedido.id)
    ledger.expira_at = clock.now() - timedelta(minutes=1)
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
    ledger = await _compromiso(db, pedido.id)
    ledger.expira_at = clock.now() - timedelta(minutes=1)
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
    """Con el servicio materializado ya no hay reserva pendiente que vencer."""
    pedido = await _aprobado(client, db, catedra, usuario_catedra, template, auth_admin)
    servicio = await factories.crear_servicio(
        db,
        catedra_id=catedra.id,
        template_id=template.id,
        pedido_id=pedido.id,
        proxmox_vmid="190",
    )
    ledger = await _compromiso(db, pedido.id)
    ledger.servicio_id = servicio.id
    ledger.estado = "materializado"
    ledger.expira_at = None
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


async def test_009_future_approval_reserves_now_and_expires_after_start(
    client, db, perfil_capacidad, catedra, usuario_catedra, template, auth_admin
):
    now = clock.now()
    start = now.astimezone(ZoneInfo("America/Argentina/Tucuman")).date() + timedelta(days=10)
    pedido = await preparar_pedido(db, catedra, usuario_catedra, template)
    payload = seleccion(template, desde=start, hasta=start + timedelta(days=5))
    evaluation = await client.post(
        f"/pedidos/{pedido.id}/evaluacion", headers=auth_admin, json=payload
    )
    assert evaluation.status_code == 200, evaluation.text
    response = await client.post(
        f"/pedidos/{pedido.id}/aprobar",
        headers=auth_admin | {"Idempotency-Key": "future-approval"},
        json={**payload, "capacidad_token": evaluation.json()["capacidad_token"]},
    )
    assert response.status_code == 200, response.text
    ledger = await _compromiso(db, pedido.id)
    period = resolver_fechas(start, start + timedelta(days=5), "America/Argentina/Tucuman")
    assert db_utc(ledger.expira_at) == period.inicio_at + timedelta(hours=24)
    denied = await client.post(
        f"/servicios/desplegar/{pedido.id}",
        headers=auth_admin | {"Idempotency-Key": "future-denied"},
        json={},
    )
    assert denied.status_code == 409
    assert denied.json()["detail"]["codigo"] == "inicio_futuro"


def test_009_expiration_is_bounded_by_authorized_end():
    period = resolver_fechas(date(2027, 3, 1), date(2027, 3, 1), "America/Argentina/Tucuman")
    approval = datetime(2027, 3, 1, 20, tzinfo=timezone.utc)
    assert expiracion_reserva(period, approval) == period.fin_exclusivo_at
