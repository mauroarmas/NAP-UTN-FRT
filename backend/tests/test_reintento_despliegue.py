"""US1 — máquina de estados del reintento de despliegue."""

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.pedido import EstadoPedido, PedidoHistorial
from app.models.servicio import Servicio
from app.services import bootstrap_service
from app.worker import procesar_una
from tests import factories
from tests.capacity_helpers import aprobar_http, perfil_capacidad  # noqa: F401
from tests.test_operaciones_recuperacion import prepared_guest  # noqa: F401


async def _pedido_fallido_en_bootstrap(
    client, engine, db, proxmox, catedra, usuario_catedra, template, auth_admin, monkeypatch
):
    pedido = await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario_catedra.id,
        template_id=template.id,
        estado=EstadoPedido.SOLICITADO,
    )
    r_ap = await aprobar_http(client, pedido, template, auth_admin)
    assert r_ap.status_code == 200, r_ap.text
    r_dep = await client.post(
        f"/servicios/desplegar/{pedido.id}",
        headers=auth_admin | {"Idempotency-Key": f"dep-{uuid4()}"},
        json={},
    )
    assert r_dep.status_code == 202, r_dep.text

    async def _fallar(*args, **kwargs):
        return {"identity_verified": False, "local_health": False}

    monkeypatch.setattr(bootstrap_service, "preparar", _fallar)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await procesar_una(sessions, pve=proxmox)
    await db.refresh(pedido)
    assert pedido.estado == EstadoPedido.ERROR
    return pedido, sessions


async def _restaurar_bootstrap(monkeypatch):
    async def _ok(*args, **kwargs):
        return {
            "identity_verified": True,
            "local_health": True,
            "acceso_metadata": {"metodo": "consola", "validacion": "simulada"},
        }

    monkeypatch.setattr(bootstrap_service, "preparar", _ok)


async def test_reintento_exitoso_deja_el_pedido_reparado_sin_recrear(
    client, engine, db, proxmox, catedra, usuario_catedra, template, auth_admin,
    perfil_capacidad, prepared_guest, monkeypatch
):
    """El reintento repara sobre la identidad existente y confirma el servicio."""
    pedido, sessions = await _pedido_fallido_en_bootstrap(
        client, engine, db, proxmox, catedra, usuario_catedra, template, auth_admin, monkeypatch
    )
    await _restaurar_bootstrap(monkeypatch)

    r = await client.post(
        f"/pedidos/{pedido.id}/reintentar",
        headers=auth_admin | {"Idempotency-Key": "reintento-ok-1"},
        json={"motivo": "Reintento tras revisar bootstrap"},
    )
    assert r.status_code == 202, r.text
    await procesar_una(sessions, pve=proxmox)

    servicio = await db.scalar(select(Servicio).where(Servicio.pedido_id == pedido.id))
    assert servicio is not None
    assert servicio.proxmox_vmid is not None
    assert len(proxmox.creados) == 1


async def test_reintento_fallido_conserva_historial_anterior(
    client, engine, db, proxmox, catedra, usuario_catedra, template, auth_admin,
    perfil_capacidad, prepared_guest, monkeypatch
):
    """US1 esc. 2 / FR-005 — un reintento que falla agrega historial, no lo pisa."""
    pedido, sessions = await _pedido_fallido_en_bootstrap(
        client, engine, db, proxmox, catedra, usuario_catedra, template, auth_admin, monkeypatch
    )

    r = await client.post(
        f"/pedidos/{pedido.id}/reintentar",
        headers=auth_admin | {"Idempotency-Key": "reintento-falla-1"},
        json={"motivo": "Reintento aún con fallo"},
    )
    assert r.status_code == 202, r.text
    await procesar_una(sessions, pve=proxmox)

    await db.refresh(pedido)
    assert pedido.estado == EstadoPedido.ERROR

    filas = (
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
    assert len(filas) >= 4
    transiciones = [(f.estado_anterior, f.estado_nuevo) for f in filas]
    assert transiciones.count(("en_despliegue", "error")) == 2


@pytest.mark.parametrize(
    "estado", [EstadoPedido.ACTIVO, EstadoPedido.RECHAZADO, EstadoPedido.APROBADO]
)
async def test_reintento_sobre_estado_invalido_responde_409(
    client, db, proxmox, catedra, usuario_catedra, template, auth_admin, estado, perfil_capacidad
):
    """US1 esc. 3 / FR-002 — solo se reintenta desde ERROR."""
    pedido = await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario_catedra.id,
        template_id=template.id,
        estado=estado,
    )

    r = await client.post(
        f"/pedidos/{pedido.id}/reintentar",
        headers=auth_admin | {"Idempotency-Key": f"reintento-inv-{estado.value}"},
        json={},
    )

    assert r.status_code == 409, r.text
    assert r.json()["detail"]["codigo"] == "estado_incompatible"
    assert proxmox.creados == []


async def test_reintento_de_pedido_inexistente_responde_404(client, proxmox, auth_admin):
    r = await client.post(
        "/pedidos/9999/reintentar",
        headers=auth_admin | {"Idempotency-Key": "reintento-404"},
        json={},
    )
    assert r.status_code == 404


async def test_varios_reintentos_registran_cada_intento(
    client, engine, db, proxmox, catedra, usuario_catedra, template, auth_admin,
    perfil_capacidad, prepared_guest, monkeypatch
):
    """US1 esc. 6 — cada intento queda como entrada distinta y ordenada."""
    pedido, sessions = await _pedido_fallido_en_bootstrap(
        client, engine, db, proxmox, catedra, usuario_catedra, template, auth_admin, monkeypatch
    )

    r1 = await client.post(
        f"/pedidos/{pedido.id}/reintentar",
        headers=auth_admin | {"Idempotency-Key": "reintento-seq-1"},
        json={},
    )
    assert r1.status_code == 202
    await procesar_una(sessions, pve=proxmox)
    await db.refresh(pedido)
    assert pedido.estado == EstadoPedido.ERROR

    await _restaurar_bootstrap(monkeypatch)
    r2 = await client.post(
        f"/pedidos/{pedido.id}/reintentar",
        headers=auth_admin | {"Idempotency-Key": "reintento-seq-2"},
        json={},
    )
    assert r2.status_code == 202, r2.text
    await procesar_una(sessions, pve=proxmox)

    filas = (
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
    transiciones = [(f.estado_anterior, f.estado_nuevo) for f in filas]
    assert transiciones.count(("error", "en_despliegue")) == 2
    assert transiciones.count(("en_despliegue", "error")) == 2
    assert len(proxmox.creados) == 1
