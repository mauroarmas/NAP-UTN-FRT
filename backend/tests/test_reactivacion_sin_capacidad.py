"""Reactivación de un servicio pausado por la propia cátedra."""

from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.servicio import EstadoServicio
from app.models.servicio_historial import ServicioHistorial
from app.worker import procesar_una
from tests import factories
from tests.capacity_helpers import GIB, materializado, perfil_capacidad  # noqa: F401


@pytest.fixture(autouse=True)
def cluster(proxmox, perfil_capacidad):
    return proxmox


async def _pausado(db, proxmox, catedra, usuario, template, vmid=500, vcpus=2, ram_mb=1024, disk_gb=10):
    servicio, ledger = await materializado(
        db, proxmox, catedra, usuario, template, vmid=int(vmid), vcpus=vcpus
    )
    servicio.ram_asignada_mb = ram_mb
    servicio.disk_asignado_gb = disk_gb
    servicio.asignacion_snapshot = {
        **servicio.asignacion_snapshot,
        "ram_mb": ram_mb,
        "disk_gb": disk_gb,
    }
    proxmox.configuraciones[("pve1", int(vmid))]["memory"] = ram_mb
    proxmox.configuraciones[("pve1", int(vmid))]["rootfs"] = f"local-lvm:vm-{int(vmid)}-disk-0,size={disk_gb}G"
    for r in proxmox.recursos:
        if int(r["vmid"]) == int(vmid):
            r["maxmem"] = ram_mb * 1024 * 1024
    servicio.pausado_auto_at = datetime.utcnow()
    await db.commit()
    return servicio


async def test_la_catedra_reactiva_su_servicio_sin_aprobacion(
    client, engine, db, proxmox, catedra, usuario_catedra, template, auth_catedra
):
    servicio = await _pausado(db, proxmox, catedra, usuario_catedra, template, vmid=500)

    r = await client.post(
        f"/servicios/{servicio.id}/reactivar",
        headers=auth_catedra | {"Idempotency-Key": f"react-{uuid4()}"},
        json={},
    )

    assert r.status_code == 202, r.text
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await procesar_una(sessions, pve=proxmox)

    await db.refresh(servicio)
    assert servicio.estado == EstadoServicio.RUNNING
    assert servicio.pausado_auto_at is None
    assert ("pve1", 500) in proxmox.iniciados


async def test_reactivar_limpia_la_pausa_programada(
    client, engine, db, proxmox, catedra, usuario_catedra, template, auth_catedra
):
    servicio = await _pausado(db, proxmox, catedra, usuario_catedra, template, vmid=501)
    servicio.pausa_programada_at = datetime.utcnow()
    servicio.aviso_pausa_at = datetime.utcnow()
    await db.commit()

    r = await client.post(
        f"/servicios/{servicio.id}/reactivar",
        headers=auth_catedra | {"Idempotency-Key": f"react-{uuid4()}"},
        json={},
    )
    assert r.status_code == 202, r.text
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await procesar_una(sessions, pve=proxmox)

    await db.refresh(servicio)
    assert servicio.pausa_programada_at is None
    assert servicio.aviso_pausa_at is None


async def test_la_reactivacion_queda_en_el_historial_con_su_autor(
    client, engine, db, proxmox, catedra, template, auth_catedra, usuario_catedra
):
    servicio = await _pausado(db, proxmox, catedra, usuario_catedra, template, vmid=502)

    r = await client.post(
        f"/servicios/{servicio.id}/reactivar",
        headers=auth_catedra | {"Idempotency-Key": f"react-{uuid4()}"},
        json={},
    )
    assert r.status_code == 202, r.text
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await procesar_una(sessions, pve=proxmox)

    entradas = (
        (
            await db.execute(
                select(ServicioHistorial)
                .where(ServicioHistorial.servicio_id == servicio.id)
                .order_by(ServicioHistorial.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(entradas) >= 2
    assert entradas[0].usuario_id == usuario_catedra.id
    assert entradas[-1].estado_nuevo == EstadoServicio.RUNNING.value


async def test_sin_capacidad_queda_pausado_y_no_en_error(
    client, db, proxmox, catedra, usuario_catedra, template, auth_catedra
):
    """El escenario que la spec exige que no deje el servicio en estado ambiguo."""
    servicio = await _pausado(
        db, proxmox, catedra, usuario_catedra, template, vmid=503, vcpus=8, ram_mb=16384
    )
    proxmox.nodos = [{"node": "pve1", "status": "online", "maxcpu": 2, "maxmem": 2 * GIB, "mem": GIB}]

    r = await client.post(
        f"/servicios/{servicio.id}/reactivar",
        headers=auth_catedra | {"Idempotency-Key": f"react-{uuid4()}"},
        json={},
    )

    assert r.status_code == 409, r.text
    assert r.json()["detail"]["codigo"] == "sin_capacidad"

    await db.refresh(servicio)
    assert servicio.estado == EstadoServicio.PAUSED, "nunca en error"
    assert servicio.pausado_auto_at is not None
    assert proxmox.iniciados == [], "no debe tocarse la infraestructura si no hay lugar"


async def test_un_fallo_de_infraestructura_da_502(
    client, db, proxmox, catedra, usuario_catedra, template, auth_catedra
):
    servicio = await _pausado(db, proxmox, catedra, usuario_catedra, template, vmid=504)
    proxmox.nodos = [{"node": "pve1", "status": "offline", "maxcpu": 8, "maxmem": 16 * GIB, "mem": 0}]

    r = await client.post(
        f"/servicios/{servicio.id}/reactivar",
        headers=auth_catedra | {"Idempotency-Key": f"react-{uuid4()}"},
        json={},
    )

    assert r.status_code == 502, r.text
    await db.refresh(servicio)
    assert servicio.estado == EstadoServicio.PAUSED


async def test_no_se_reactiva_lo_que_no_esta_pausado(
    client, db, proxmox, catedra, usuario_catedra, template, auth_catedra
):
    servicio = await _pausado(db, proxmox, catedra, usuario_catedra, template, vmid=505)
    servicio.estado = EstadoServicio.RUNNING
    await db.commit()

    r = await client.post(
        f"/servicios/{servicio.id}/reactivar",
        headers=auth_catedra | {"Idempotency-Key": f"react-{uuid4()}"},
        json={},
    )

    assert r.status_code == 409, r.text


async def test_no_se_reactiva_un_servicio_ajeno(
    client, db, proxmox, template, auth_catedra, usuario_multicatedra
):
    ajeno = await _pausado(
        db, proxmox, usuario_multicatedra.ajena, usuario_multicatedra.ajeno, template, vmid=506
    )

    r = await client.post(
        f"/servicios/{ajeno.id}/reactivar",
        headers=auth_catedra | {"Idempotency-Key": f"react-{uuid4()}"},
        json={},
    )

    assert r.status_code == 403, r.text


# --- Marca "siempre encendido" y listados del administrador ---


async def test_la_catedra_marca_su_servicio_como_siempre_encendido(
    client, db, proxmox, catedra, template, auth_catedra
):
    servicio = await factories.crear_servicio(
        db, catedra_id=catedra.id, template_id=template.id, proxmox_vmid="510"
    )

    r = await client.patch(
        f"/servicios/{servicio.id}",
        json={"exento_pausado": True},
        headers=auth_catedra,
    )

    assert r.status_code == 200, r.text
    assert r.json()["exento_pausado"] is True


async def test_marcar_exento_cancela_la_pausa_anunciada(
    client, db, proxmox, catedra, template, auth_catedra
):
    """Avisar de una pausa que ya no va a ocurrir sería incoherente."""
    servicio = await factories.crear_servicio(
        db, catedra_id=catedra.id, template_id=template.id, proxmox_vmid="511"
    )
    servicio.pausa_programada_at = datetime.utcnow()
    servicio.aviso_pausa_at = datetime.utcnow()
    await db.commit()

    await client.patch(
        f"/servicios/{servicio.id}",
        json={"exento_pausado": True},
        headers=auth_catedra,
    )

    await db.refresh(servicio)
    assert servicio.pausa_programada_at is None


async def test_la_catedra_no_puede_cambiar_el_vencimiento(
    client, db, proxmox, catedra, template, auth_catedra
):
    """Correr una fecha de fin es una decisión sobre capacidad (rechazado por schema cerrado)."""
    servicio = await factories.crear_servicio(
        db, catedra_id=catedra.id, template_id=template.id, proxmox_vmid="512"
    )

    r = await client.patch(
        f"/servicios/{servicio.id}",
        json={"vence_at": "2030-01-01T00:00:00"},
        headers=auth_catedra,
    )

    assert r.status_code in {403, 422}, r.text


async def test_el_admin_ve_los_pausados_con_su_antiguedad(
    client, db, proxmox, catedra, usuario_catedra, template, auth_admin
):
    await _pausado(db, proxmox, catedra, usuario_catedra, template, vmid=520, disk_gb=8)

    r = await client.get("/servicios/pausados", headers=auth_admin)

    assert r.status_code == 200, r.text
    fila = r.json()[0]
    assert fila["dias_pausado"] == 0
    assert fila["disk_asignado_gb"] == 8


async def test_los_pausados_son_solo_para_el_admin(client, auth_catedra):
    r = await client.get("/servicios/pausados", headers=auth_catedra)

    assert r.status_code == 403, r.text


async def test_el_admin_ve_los_exentos_que_igual_estan_inactivos(
    client, db, proxmox, catedra, template, auth_admin
):
    """Contrapeso a que la exención se use de más."""
    from tests.test_inactividad_pausado import _sembrar

    servicio = await factories.crear_servicio(
        db,
        catedra_id=catedra.id,
        template_id=template.id,
        proxmox_vmid="530",
        estado=EstadoServicio.RUNNING,
    )
    servicio.exento_pausado = True
    await db.commit()
    await _sembrar(db, servicio.id)

    r = await client.get("/servicios/exentos-inactivos", headers=auth_admin)

    assert r.status_code == 200, r.text
    assert [s["id"] for s in r.json()] == [servicio.id]
