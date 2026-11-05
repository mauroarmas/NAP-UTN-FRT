"""Vencimiento de servicios y renovación por el mismo circuito de aprobación."""

from datetime import timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.pedido import EstadoPedido, Pedido, TipoPedido
from app.models.servicio import EstadoServicio
from app.models.servicio_historial import ServicioHistorial
from app.models.vigencia import VigenciaAutorizada
from app.services import capacidad_service, vencimiento_service, vigencia_service
from app.utils.clock import clock
from app.worker import procesar_una
from tests import factories
from tests.capacity_helpers import aprobar_http, materializado, perfil_capacidad, preparar_pedido  # noqa: F401
from tests.test_operaciones_recuperacion import prepared_guest  # noqa: F401


@pytest.fixture(autouse=True)
def cluster(proxmox, perfil_capacidad):
    return proxmox


async def _servicio_con_vencimiento(
    db, proxmox, catedra, usuario, template, vence_en_dias, vmid="600", estado=EstadoServicio.RUNNING
):
    vmid_int = int(vmid)
    servicio, ledger = await materializado(
        db, proxmox, catedra, usuario, template, vmid=vmid_int
    )
    servicio.estado = estado
    if estado == EstadoServicio.RUNNING:
        ledger.vcpus_retenidos = servicio.vcpus_asignados
        ledger.ram_mb_retenida = servicio.ram_asignada_mb
        proxmox.estados[vmid_int] = "running"
        for r in proxmox.recursos:
            if int(r["vmid"]) == vmid_int:
                r["status"] = "running"
    today = clock.now().astimezone(ZoneInfo("America/Argentina/Tucuman")).date()
    hasta = today + timedelta(days=vence_en_dias)
    desde = hasta - timedelta(days=30)
    period = vigencia_service.resolver_fechas(desde, hasta, "America/Argentina/Tucuman")
    vig = await db.scalar(
        select(VigenciaAutorizada).where(VigenciaAutorizada.servicio_id == servicio.id)
    )
    vig.desde_local = period.desde
    vig.hasta_local = period.hasta
    vig.inicio_at = period.inicio_at
    vig.fin_exclusivo_at = period.fin_exclusivo_at
    servicio.vence_at = period.fin_exclusivo_at.replace(tzinfo=None)
    await db.commit()
    return servicio


def _vigencia_renovacion_posterior(servicio_vence_at):
    desde = servicio_vence_at.date() + timedelta(days=1)
    hasta = desde + timedelta(days=30)
    return {
        "tipo": "personalizado",
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
    }


def _seleccion_renovacion(servicio, vig):
    return {
        "asignacion": servicio.asignacion_snapshot,
        "destino": {"nodo": "pve1", "storage": "local-lvm"},
        "vigencia": vig,
    }


# --- El servicio nace con fecha conocida ---


async def test_el_servicio_desplegado_nace_con_fecha_de_vencimiento(
    client, engine, db, proxmox, catedra, usuario_catedra, template, auth_admin, prepared_guest
):
    pedido = await preparar_pedido(db, catedra, usuario_catedra, template)
    await aprobar_http(client, pedido, template, auth_admin, clave=f"apr-{uuid4()}")

    r = await client.post(
        f"/servicios/desplegar/{pedido.id}",
        headers=auth_admin | {"Idempotency-Key": f"dep-{uuid4()}"},
        json={},
    )
    assert r.status_code == 202, r.text
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await procesar_una(sessions, pve=proxmox)
    db.expire_all()

    await db.refresh(pedido)
    assert pedido.servicio_id is not None
    srv_resp = await client.get(f"/servicios/{pedido.servicio_id}", headers=auth_admin)
    assert srv_resp.status_code == 200, srv_resp.text
    assert srv_resp.json()["vence_at"] is not None, (
        "la cátedra tiene que saber desde el primer día hasta cuándo lo tiene"
    )


# --- Renovación ---


async def test_la_catedra_solicita_una_renovacion(
    client, db, proxmox, catedra, usuario_catedra, template, auth_catedra
):
    servicio = await _servicio_con_vencimiento(
        db, proxmox, catedra, usuario_catedra, template, 3
    )
    vig = _vigencia_renovacion_posterior(servicio.vence_at)

    r = await client.post(
        f"/servicios/{servicio.id}/renovar",
        headers=auth_catedra | {"Idempotency-Key": f"ren-{uuid4()}"},
        json={"vigencia": vig},
    )

    assert r.status_code == 201, r.text
    assert r.json()["servicio_id"] == servicio.id

    pedido = await db.get(Pedido, r.json()["pedido_id"])
    assert pedido.tipo == TipoPedido.RENOVACION
    assert pedido.estado == EstadoPedido.SOLICITADO


async def test_no_se_puede_pedir_dos_renovaciones_a_la_vez(
    client, db, proxmox, catedra, usuario_catedra, template, auth_catedra
):
    servicio = await _servicio_con_vencimiento(
        db, proxmox, catedra, usuario_catedra, template, 3, vmid="601"
    )
    vig = _vigencia_renovacion_posterior(servicio.vence_at)
    await client.post(
        f"/servicios/{servicio.id}/renovar",
        headers=auth_catedra | {"Idempotency-Key": f"ren1-{uuid4()}"},
        json={"vigencia": vig},
    )

    segunda = await client.post(
        f"/servicios/{servicio.id}/renovar",
        headers=auth_catedra | {"Idempotency-Key": f"ren2-{uuid4()}"},
        json={"vigencia": vig},
    )

    assert segunda.status_code == 409, segunda.text


async def test_la_renovacion_no_reserva_capacidad_nueva(
    client, db, proxmox, catedra, usuario_catedra, template, auth_catedra, auth_admin
):
    """El servicio ya está desplegado y ya cuenta como consumo."""
    servicio = await _servicio_con_vencimiento(
        db, proxmox, catedra, usuario_catedra, template, 3, vmid="602"
    )
    vig = _vigencia_renovacion_posterior(servicio.vence_at)
    r = await client.post(
        f"/servicios/{servicio.id}/renovar",
        headers=auth_catedra | {"Idempotency-Key": f"ren-{uuid4()}"},
        json={"vigencia": vig},
    )
    pedido = await db.get(Pedido, r.json()["pedido_id"])

    antes = await capacidad_service.panorama(db)
    res_apr = await aprobar_http(
        client,
        pedido,
        template,
        auth_admin,
        clave=f"apr-ren-{uuid4()}",
        payload=_seleccion_renovacion(servicio, vig),
    )
    assert res_apr.status_code == 200, res_apr.text
    despues = await capacidad_service.panorama(db)

    assert despues["reservado"] == antes["reservado"], (
        "contar la renovación como reserva sería contabilidad doble"
    )


async def test_la_renovacion_aprobada_conserva_el_servicio_y_corre_la_fecha(
    client, db, proxmox, catedra, usuario_catedra, template, auth_catedra, auth_admin
):
    """Recrear el servicio le haría perder a la cátedra todo lo que tenía adentro."""
    servicio = await _servicio_con_vencimiento(
        db, proxmox, catedra, usuario_catedra, template, 3, vmid="603"
    )
    id_original = servicio.id
    vmid_original = servicio.proxmox_vmid
    vence_original = servicio.vence_at
    vig = _vigencia_renovacion_posterior(servicio.vence_at)

    r = await client.post(
        f"/servicios/{servicio.id}/renovar",
        headers=auth_catedra | {"Idempotency-Key": f"ren-{uuid4()}"},
        json={"vigencia": vig},
    )
    pedido = await db.get(Pedido, r.json()["pedido_id"])
    aprobado = await aprobar_http(
        client,
        pedido,
        template,
        auth_admin,
        clave=f"apr-ren-{uuid4()}",
        payload=_seleccion_renovacion(servicio, vig),
    )

    assert aprobado.status_code == 200, aprobado.text
    await db.refresh(servicio)
    assert servicio.id == id_original, "no se recrea el servicio"
    assert servicio.proxmox_vmid == vmid_original, "no se recrea el contenedor"
    assert servicio.vence_at > vence_original, "solo corre la fecha"


async def test_la_renovacion_queda_en_el_historial_del_servicio(
    client, db, proxmox, catedra, usuario_catedra, template, auth_catedra, auth_admin
):
    servicio = await _servicio_con_vencimiento(
        db, proxmox, catedra, usuario_catedra, template, 3, vmid="604"
    )
    vig = _vigencia_renovacion_posterior(servicio.vence_at)
    r = await client.post(
        f"/servicios/{servicio.id}/renovar",
        headers=auth_catedra | {"Idempotency-Key": f"ren-{uuid4()}"},
        json={"vigencia": vig},
    )
    pedido = await db.get(Pedido, r.json()["pedido_id"])
    await aprobar_http(
        client,
        pedido,
        template,
        auth_admin,
        clave=f"apr-ren-{uuid4()}",
        payload=_seleccion_renovacion(servicio, vig),
    )

    entradas = (
        (
            await db.execute(
                select(ServicioHistorial).where(
                    ServicioHistorial.servicio_id == servicio.id
                )
            )
        )
        .scalars()
        .all()
    )
    assert any("renovación" in (e.comentario or "").lower() for e in entradas)


async def test_la_renovacion_rechazada_deja_ver_el_motivo(
    client, db, proxmox, catedra, usuario_catedra, template, auth_catedra, auth_admin
):
    servicio = await _servicio_con_vencimiento(
        db, proxmox, catedra, usuario_catedra, template, 3, vmid="605"
    )
    vig = _vigencia_renovacion_posterior(servicio.vence_at)
    r = await client.post(
        f"/servicios/{servicio.id}/renovar",
        headers=auth_catedra | {"Idempotency-Key": f"ren-{uuid4()}"},
        json={"vigencia": vig},
    )
    pedido_id = r.json()["pedido_id"]

    await client.post(
        f"/pedidos/{pedido_id}/rechazar",
        json={"motivo": "La materia termina este cuatrimestre"},
        headers=auth_admin | {"Idempotency-Key": f"rej-ren-{uuid4()}"},
    )

    visto = await client.get(f"/pedidos/{pedido_id}", headers=auth_catedra)
    assert "cuatrimestre" in visto.json()["motivo_rechazo"]


async def test_no_se_renueva_un_servicio_ajeno(
    client, db, proxmox, template, auth_catedra, usuario_multicatedra
):
    ajeno = await factories.crear_servicio(
        db,
        catedra_id=usuario_multicatedra.ajena.id,
        template_id=template.id,
        proxmox_vmid="606",
    )

    r = await client.post(
        f"/servicios/{ajeno.id}/renovar",
        headers=auth_catedra | {"Idempotency-Key": f"ren-{uuid4()}"},
        json={"vigencia": {"tipo": "personalizado", "desde": "2026-07-01", "hasta": "2026-08-01"}},
    )

    assert r.status_code == 403, r.text


# --- Aplicación del vencimiento ---


async def test_avisa_antes_de_vencer(db, proxmox, catedra, usuario_catedra, template):
    servicio = await _servicio_con_vencimiento(
        db, proxmox, catedra, usuario_catedra, template, 3, vmid="610"
    )

    resultado = await vencimiento_service.aplicar_vencimientos(db)

    assert servicio.id in resultado["avisados"]
    assert resultado["afectados"] == 0
    await db.refresh(servicio)
    assert servicio.aviso_vencimiento_at is not None
    assert servicio.estado == EstadoServicio.RUNNING


async def test_el_servicio_vencido_libera_computo_sin_destruir_datos(
    engine, db, proxmox, catedra, usuario_catedra, template
):
    servicio = await _servicio_con_vencimiento(
        db, proxmox, catedra, usuario_catedra, template, -2, vmid="611"
    )

    resultado = await vencimiento_service.aplicar_vencimientos(db)
    assert resultado["afectados"] == 1
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await procesar_una(sessions, pve=proxmox)
    db.expire_all()

    await db.refresh(servicio)
    assert servicio.estado == EstadoServicio.PAUSED
    assert servicio.deleted_at is None, "los datos no se destruyen automáticamente"
    assert ("pve1", 611) in proxmox.detenidos


async def test_el_vencimiento_queda_registrado_con_el_sistema_como_autor(
    engine, db, proxmox, catedra, usuario_catedra, template
):
    servicio = await _servicio_con_vencimiento(
        db, proxmox, catedra, usuario_catedra, template, -2, vmid="612"
    )
    servicio_id = servicio.id

    await vencimiento_service.aplicar_vencimientos(db)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await procesar_una(sessions, pve=proxmox)
    db.expire_all()

    entradas = (
        (
            await db.execute(
                select(ServicioHistorial).where(
                    ServicioHistorial.servicio_id == servicio_id
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(entradas) >= 1
    assert all(e.usuario_id is None for e in entradas)


async def test_un_servicio_ya_pausado_no_descuenta_capacidad_dos_veces(
    db, proxmox, catedra, usuario_catedra, template
):
    """Vencimiento y pausado pueden alcanzar al mismo servicio."""
    servicio = await _servicio_con_vencimiento(
        db,
        proxmox,
        catedra,
        usuario_catedra,
        template,
        -2,
        vmid="613",
        estado=EstadoServicio.PAUSED,
    )
    servicio.pausado_auto_at = clock.now().replace(tzinfo=None)
    await db.commit()

    antes = await capacidad_service.panorama(db)
    resultado = await vencimiento_service.aplicar_vencimientos(db)
    despues = await capacidad_service.panorama(db)

    assert resultado["afectados"] == 0
    assert despues["desplegado"] == antes["desplegado"], (
        "la pausa ya había liberado el cómputo; no hay nada que descontar otra vez"
    )
    assert proxmox.detenidos == [], "no hay que volver a detener lo ya detenido"


async def test_sin_fecha_de_vencimiento_no_se_apaga_nada(
    db, proxmox, catedra, template
):
    """Los servicios sin período de vigencia regularizado se omiten sin apagarse."""
    await factories.crear_servicio(
        db, catedra_id=catedra.id, template_id=template.id, proxmox_vmid="614"
    )

    resultado = await vencimiento_service.aplicar_vencimientos(db)

    assert resultado["afectados"] == 0
    assert proxmox.detenidos == []


async def test_el_trabajo_es_ejecutable_a_mano(client, auth_admin):
    r = await client.post("/admin/jobs/aplicar_vencimientos", headers=auth_admin)

    assert r.status_code == 200, r.text
    assert r.json()["job"] == "aplicar_vencimientos"
