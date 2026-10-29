"""US2 — baja lógica de servicios (FR-007 a FR-010)."""

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.servicio import EstadoServicio, Servicio
from app.worker import procesar_una
from tests import factories
from tests.capacity_helpers import materializado, perfil_capacidad  # noqa: F401
from tests.fakes import ProxmoxFalla


@pytest.fixture(autouse=True)
def cluster(proxmox, perfil_capacidad):
    return proxmox


async def _servicio(
    db, proxmox, catedra, usuario_catedra, template, proxmox_vmid="120", estado=EstadoServicio.STOPPED
):
    vmid = int(proxmox_vmid)
    servicio, ledger = await materializado(
        db, proxmox, catedra, usuario_catedra, template, vmid=vmid
    )
    servicio.estado = estado
    if estado == EstadoServicio.RUNNING:
        ledger.vcpus_retenidos = servicio.vcpus_asignados
        ledger.ram_mb_retenida = servicio.ram_asignada_mb
        proxmox.estados[vmid] = "running"
        for r in proxmox.recursos:
            if int(r["vmid"]) == vmid:
                r["status"] = "running"
    await db.commit()
    return servicio


async def _ejecutar_baja(client, engine, db, proxmox, servicio_id, auth_admin):
    r = await client.delete(
        f"/servicios/{servicio_id}",
        headers=auth_admin | {"Idempotency-Key": f"del-srv-{uuid4()}"},
    )
    if r.status_code == 202:
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        await procesar_una(sessions, pve=proxmox)
        await procesar_una(sessions, pve=proxmox)
        db.expire_all()
    return r


async def test_baja_libera_el_contenedor_y_conserva_la_fila(
    client, engine, db, proxmox, catedra, usuario_catedra, template, auth_admin
):
    """US2 esc. 1 / FR-007, FR-008 — se libera en Proxmox y la fila permanece."""
    servicio = await _servicio(
        db, proxmox, catedra, usuario_catedra, template, proxmox_vmid="120", estado=EstadoServicio.RUNNING
    )
    servicio_id = servicio.id
    pedido_id = servicio.pedido_id
    from app.models.pedido import Pedido
    pedido = await db.get(Pedido, pedido_id)
    pedido.servicio_id = servicio_id
    await db.commit()
    before = await client.get(f'/pedidos/{pedido_id}', headers=auth_admin)
    assert before.status_code == 200
    assert before.json()['servicio_dado_de_baja'] is False

    r = await _ejecutar_baja(client, engine, db, proxmox, servicio_id, auth_admin)

    assert r.status_code == 202, r.text
    assert ("pve1", 120) in proxmox.eliminados

    fila = (
        await db.execute(select(Servicio).where(Servicio.id == servicio_id))
    ).scalar_one()
    await db.refresh(fila)
    assert fila.deleted_at is not None
    assert fila.vcpus_asignados >= 1
    assert fila.ram_asignada_mb >= 512
    detail = await client.get(f'/pedidos/{pedido_id}', headers=auth_admin)
    assert detail.status_code == 200
    assert detail.json()['servicio_dado_de_baja'] is True
    assert detail.json()['estado'] == 'activo'  # La aprobación histórica se conserva.
    listing = await client.get('/pedidos/', headers=auth_admin)
    assert next(p for p in listing.json() if p['id'] == pedido_id)['servicio_dado_de_baja'] is True


async def test_servicio_dado_de_baja_desaparece_de_listados(
    client, engine, db, proxmox, catedra, usuario_catedra, template, auth_admin
):
    """US2 esc. 2 / FR-009 — fuera de los listados y 404 en el detalle."""
    servicio = await _servicio(db, proxmox, catedra, usuario_catedra, template, proxmox_vmid="121")
    servicio_id = servicio.id
    await _ejecutar_baja(client, engine, db, proxmox, servicio_id, auth_admin)

    listado = await client.get("/servicios/", headers=auth_admin)
    assert listado.status_code == 200
    assert all(s["id"] != servicio_id for s in listado.json())

    detalle = await client.get(f"/servicios/{servicio_id}", headers=auth_admin)
    assert detalle.status_code == 404

    estado = await client.get(f"/servicios/{servicio_id}/status", headers=auth_admin)
    assert estado.status_code == 404


async def test_fallo_de_proxmox_no_marca_la_baja(
    client, engine, db, proxmox, catedra, usuario_catedra, template, auth_admin
):
    """FR-010 — si no se pudo liberar el recurso real, no se marca como dado de baja."""
    servicio = await _servicio(db, proxmox, catedra, usuario_catedra, template, proxmox_vmid="122")
    proxmox.fallar_delete = ProxmoxFalla("el nodo no responde")

    r = await _ejecutar_baja(client, engine, db, proxmox, servicio.id, auth_admin)

    assert r.status_code == 202, r.text
    await db.refresh(servicio)
    assert servicio.deleted_at is None, (
        "no debe marcarse la baja si el contenedor sigue vivo en el clúster"
    )


async def test_doble_baja_es_idempotente(
    client, engine, db, proxmox, catedra, usuario_catedra, template, auth_admin
):
    """US2 esc. 5 — repetir la baja no falla."""
    servicio = await _servicio(db, proxmox, catedra, usuario_catedra, template, proxmox_vmid="123")
    servicio_id = servicio.id

    r1 = await _ejecutar_baja(client, engine, db, proxmox, servicio_id, auth_admin)
    assert r1.status_code == 202
    eliminados_tras_primera = len(proxmox.eliminados)

    r2 = await client.delete(
        f"/servicios/{servicio_id}",
        headers=auth_admin | {"Idempotency-Key": f"del-srv-{uuid4()}"},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["estado"] == "retirado"
    assert r2.json()["sin_cambios"] is True
    assert len(proxmox.eliminados) == eliminados_tras_primera


async def test_servicio_dado_de_baja_no_admite_operaciones_de_ciclo_de_vida(
    client, engine, db, proxmox, catedra, usuario_catedra, template, auth_admin
):
    """Un registro dado de baja es inaccesible también para start/stop (FR-009)."""
    servicio = await _servicio(db, proxmox, catedra, usuario_catedra, template, proxmox_vmid="124")
    servicio_id = servicio.id
    await _ejecutar_baja(client, engine, db, proxmox, servicio_id, auth_admin)
    proxmox.detenidos.clear()
    proxmox.iniciados.clear()

    stop = await client.post(
        f"/servicios/{servicio_id}/stop",
        headers=auth_admin | {"Idempotency-Key": f"stop-{uuid4()}"},
        json={},
    )
    start = await client.post(
        f"/servicios/{servicio_id}/start",
        headers=auth_admin | {"Idempotency-Key": f"start-{uuid4()}"},
        json={},
    )

    assert stop.status_code in {404, 409}
    assert start.status_code in {404, 409}
    assert proxmox.detenidos == []
    assert proxmox.iniciados == []


async def test_pedido_dado_de_baja_no_se_puede_desplegar(
    client, db, proxmox, catedra, usuario_catedra, template, auth_admin
):
    """El despliegue inicial tampoco alcanza registros dados de baja."""
    from app.models.pedido import EstadoPedido

    pedido = await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario_catedra.id,
        template_id=template.id,
        estado=EstadoPedido.APROBADO,
    )
    await client.delete(
        f"/pedidos/{pedido.id}",
        headers=auth_admin | {"Idempotency-Key": f"del-ped-{uuid4()}"},
    )

    r = await client.post(
        f"/servicios/desplegar/{pedido.id}",
        headers=auth_admin | {"Idempotency-Key": f"dep-{uuid4()}"},
        json={},
    )

    assert r.status_code in {404, 409}
    assert proxmox.creados == []


async def test_contenedor_borrado_desde_proxmox_se_puede_dar_de_baja(
    client, engine, db, proxmox, catedra, usuario_catedra, template, auth_admin
):
    """Si el contenedor ya no existe, el recurso está liberado: la baja procede."""
    servicio = await _servicio(db, proxmox, catedra, usuario_catedra, template, proxmox_vmid="125")
    proxmox.recursos = [r for r in proxmox.recursos if int(r["vmid"]) != 125]
    proxmox.configuraciones.pop(("pve1", 125), None)
    proxmox.contenidos_storage[("pve1", "local-lvm")] = [
        v for v in proxmox.contenidos_storage[("pve1", "local-lvm")] if "vm-125-" not in v["volid"]
    ]
    proxmox.fallar_delete = ProxmoxFalla("Configuration file 'nodes/pve1/lxc/125.conf' does not exist")

    r = await _ejecutar_baja(client, engine, db, proxmox, servicio.id, auth_admin)

    assert r.status_code == 202, r.text
    await db.refresh(servicio)
    assert servicio.deleted_at is not None


async def test_baja_no_procede_si_no_se_puede_verificar_el_cluster(
    client, engine, db, proxmox, catedra, usuario_catedra, template, auth_admin
):
    """Ante la duda, conservador: sin poder verificar, el registro no se cierra."""
    servicio = await _servicio(db, proxmox, catedra, usuario_catedra, template, proxmox_vmid="126")
    proxmox.fallar_delete = ProxmoxFalla("timeout")
    proxmox.fallar_recursos = ProxmoxFalla("clúster inalcanzable")

    r = await _ejecutar_baja(client, engine, db, proxmox, servicio.id, auth_admin)

    assert r.status_code == 202, r.text
    await db.refresh(servicio)
    assert servicio.deleted_at is None


async def test_servicio_sin_vmid_se_da_de_baja_sin_tocar_proxmox(
    client, engine, db, proxmox, catedra, usuario_catedra, template, auth_admin
):
    """Un servicio cuyo contenedor ya está ausente se retira sin invocar delete_lxc."""
    servicio = await _servicio(db, proxmox, catedra, usuario_catedra, template, proxmox_vmid="127")
    proxmox.recursos = [r for r in proxmox.recursos if int(r["vmid"]) != 127]
    proxmox.configuraciones.pop(("pve1", 127), None)
    proxmox.contenidos_storage[("pve1", "local-lvm")] = [
        v for v in proxmox.contenidos_storage[("pve1", "local-lvm")] if "vm-127-" not in v["volid"]
    ]

    r = await _ejecutar_baja(client, engine, db, proxmox, servicio.id, auth_admin)

    assert r.status_code == 202, r.text
    assert proxmox.eliminados == []
    await db.refresh(servicio)
    assert servicio.deleted_at is not None
