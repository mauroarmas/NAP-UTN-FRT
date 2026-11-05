"""Comportamiento de vencimientos frente a renovaciones pendientes y aprobadas (Spec 009)."""

from datetime import timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.pedido import Pedido
from app.models.servicio import EstadoServicio
from app.models.vigencia import VigenciaAutorizada
from app.services import vencimiento_service, vigencia_service
from app.utils.clock import clock
from app.worker import procesar_una
from tests.capacity_helpers import aprobar_http, materializado, perfil_capacidad  # noqa: F401


@pytest.fixture(autouse=True)
def cluster(proxmox, perfil_capacidad):
    return proxmox


async def _vencido_con_renovacion(
    client, db, proxmox, catedra, usuario_catedra, template, auth_catedra, vmid
):
    vmid_int = int(vmid)
    servicio, ledger = await materializado(
        db, proxmox, catedra, usuario_catedra, template, vmid=vmid_int
    )
    servicio.estado = EstadoServicio.RUNNING
    ledger.vcpus_retenidos = servicio.vcpus_asignados
    ledger.ram_mb_retenida = servicio.ram_asignada_mb
    proxmox.estados[vmid_int] = "running"
    for r in proxmox.recursos:
        if int(r["vmid"]) == vmid_int:
            r["status"] = "running"

    today = clock.now().astimezone(ZoneInfo("America/Argentina/Tucuman")).date()
    vig = await db.scalar(
        select(VigenciaAutorizada).where(VigenciaAutorizada.servicio_id == servicio.id)
    )
    # 1. Mientras está vigente, la cátedra solicita renovación para el período siguiente
    period_activo = vigencia_service.resolver_fechas(
        today - timedelta(days=30), today + timedelta(days=2), "America/Argentina/Tucuman"
    )
    vig.desde_local = period_activo.desde
    vig.hasta_local = period_activo.hasta
    vig.inicio_at = period_activo.inicio_at
    vig.fin_exclusivo_at = period_activo.fin_exclusivo_at
    servicio.vence_at = period_activo.fin_exclusivo_at.replace(tzinfo=None)
    await db.commit()

    vig_renovacion = {
        "tipo": "personalizado",
        "desde": (today + timedelta(days=3)).isoformat(),
        "hasta": (today + timedelta(days=33)).isoformat(),
    }
    r = await client.post(
        f"/servicios/{servicio.id}/renovar",
        headers=auth_catedra | {"Idempotency-Key": f"ren-{uuid4()}"},
        json={"vigencia": vig_renovacion},
    )
    assert r.status_code == 201, r.text

    # 2. Llega el fin de la cobertura actual sin que la renovación haya sido aprobada
    period_vencido = vigencia_service.resolver_fechas(
        today - timedelta(days=30), today - timedelta(days=1), "America/Argentina/Tucuman"
    )
    vig.desde_local = period_vencido.desde
    vig.hasta_local = period_vencido.hasta
    vig.inicio_at = period_vencido.inicio_at
    vig.fin_exclusivo_at = period_vencido.fin_exclusivo_at
    servicio.vence_at = period_vencido.fin_exclusivo_at.replace(tzinfo=None)
    await db.commit()
    return servicio, r.json()["pedido_id"]


async def test_con_renovacion_pendiente_no_extiende_cobertura_sin_aprobacion(
    client, engine, db, proxmox, catedra, usuario_catedra, template, auth_catedra
):
    """En Spec 009, una solicitud de renovación pendiente no extiende la cobertura."""
    servicio, _ = await _vencido_con_renovacion(
        client, db, proxmox, catedra, usuario_catedra, template, auth_catedra, "700"
    )

    assert await vencimiento_service.tiene_renovacion_pendiente(db, servicio.id) is True
    resultado = await vencimiento_service.aplicar_vencimientos(db)
    assert resultado["afectados"] == 1
    assert servicio.id in resultado["detalle"]

    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await procesar_una(sessions, pve=proxmox)
    db.expire_all()
    await db.refresh(servicio)
    assert servicio.estado == EstadoServicio.PAUSED


async def test_la_demora_queda_visible_para_el_administrador(
    client, db, proxmox, catedra, usuario_catedra, template, auth_catedra, auth_admin
):
    """El servicio conserva la solicitud de renovación pendiente y el estado vencido visibles."""
    servicio, pedido_id = await _vencido_con_renovacion(
        client, db, proxmox, catedra, usuario_catedra, template, auth_catedra, "701"
    )

    assert await vencimiento_service.tiene_renovacion_pendiente(db, servicio.id) is True
    detalle = await client.get(f"/servicios/{servicio.id}", headers=auth_catedra)
    assert detalle.status_code == 200
    assert detalle.json()["estado_cobertura"] == "vencido"

    pedidos = await client.get("/pedidos/?estado=solicitado", headers=auth_admin)
    assert any(p["id"] == pedido_id and p["servicio_id"] == servicio.id for p in pedidos.json())


async def test_resuelta_la_renovacion_el_servicio_sigue_vivo(
    client, engine, db, proxmox, catedra, usuario_catedra, template, auth_catedra, auth_admin
):
    """Si la renovación contigua se aprueba cubriendo hoy, el servicio sigue en ejecución."""
    servicio, pedido_id = await _vencido_con_renovacion(
        client, db, proxmox, catedra, usuario_catedra, template, auth_catedra, "702"
    )
    today = clock.now().astimezone(ZoneInfo("America/Argentina/Tucuman")).date()
    vig_continua = {
        "tipo": "personalizado",
        "desde": today.isoformat(),
        "hasta": (today + timedelta(days=30)).isoformat(),
    }
    pedido = await db.get(Pedido, pedido_id)
    aprobado = await aprobar_http(
        client,
        pedido,
        template,
        auth_admin,
        clave=f"apr-ren-{uuid4()}",
        payload={
            "asignacion": servicio.asignacion_snapshot,
            "destino": {"nodo": "pve1", "storage": "local-lvm"},
            "vigencia": vig_continua,
        },
    )
    assert aprobado.status_code == 200, aprobado.text

    resultado = await vencimiento_service.aplicar_vencimientos(db)

    assert resultado["afectados"] == 0
    await db.refresh(servicio)
    assert servicio.estado == EstadoServicio.RUNNING


async def test_rechazada_la_renovacion_el_servicio_si_vence(
    client, engine, db, proxmox, catedra, usuario_catedra, template, auth_catedra, auth_admin
):
    servicio, pedido_id = await _vencido_con_renovacion(
        client, db, proxmox, catedra, usuario_catedra, template, auth_catedra, "703"
    )

    await client.post(
        f"/pedidos/{pedido_id}/rechazar",
        json={"motivo": "La materia terminó"},
        headers=auth_admin | {"Idempotency-Key": f"rej-ren-{uuid4()}"},
    )

    resultado = await vencimiento_service.aplicar_vencimientos(db)
    assert resultado["afectados"] == 1
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await procesar_una(sessions, pve=proxmox)
    db.expire_all()

    await db.refresh(servicio)
    assert servicio.estado == EstadoServicio.PAUSED
    assert servicio.deleted_at is None, "los datos siguen ahí"


async def test_sin_renovacion_pedida_el_servicio_vence(
    engine, db, proxmox, catedra, usuario_catedra, template
):
    """Contraprueba: sin nada pendiente, la fecha se aplica normalmente."""
    servicio, ledger = await materializado(
        db, proxmox, catedra, usuario_catedra, template, vmid=704
    )
    servicio.estado = EstadoServicio.RUNNING
    ledger.vcpus_retenidos = servicio.vcpus_asignados
    ledger.ram_mb_retenida = servicio.ram_asignada_mb
    proxmox.estados[704] = "running"
    for r in proxmox.recursos:
        if int(r["vmid"]) == 704:
            r["status"] = "running"
    today = clock.now().astimezone(ZoneInfo("America/Argentina/Tucuman")).date()
    period_vencido = vigencia_service.resolver_fechas(
        today - timedelta(days=30), today - timedelta(days=1), "America/Argentina/Tucuman"
    )
    vig = await db.scalar(
        select(VigenciaAutorizada).where(VigenciaAutorizada.servicio_id == servicio.id)
    )
    vig.desde_local = period_vencido.desde
    vig.hasta_local = period_vencido.hasta
    vig.inicio_at = period_vencido.inicio_at
    vig.fin_exclusivo_at = period_vencido.fin_exclusivo_at
    servicio.vence_at = period_vencido.fin_exclusivo_at.replace(tzinfo=None)
    await db.commit()

    resultado = await vencimiento_service.aplicar_vencimientos(db)
    assert resultado["afectados"] == 1
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await procesar_una(sessions, pve=proxmox)
    db.expire_all()
    await db.refresh(servicio)
    assert servicio.estado == EstadoServicio.PAUSED
