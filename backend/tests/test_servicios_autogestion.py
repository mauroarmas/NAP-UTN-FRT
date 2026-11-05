from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.servicio import EstadoServicio
from app.models.usuario import RolUsuario
from app.worker import procesar_una
from tests import factories
from tests.auth_helpers import headers_para
from tests.capacity_helpers import materializado, perfil_capacidad  # noqa: F401


@pytest.fixture(autouse=True)
def cluster(proxmox, perfil_capacidad):
    return proxmox


async def _servicio_corriendo(db, proxmox, catedra, usuario, template, vmid=105):
    servicio, ledger = await materializado(
        db, proxmox, catedra, usuario, template, vmid=vmid
    )
    servicio.estado = EstadoServicio.RUNNING
    ledger.vcpus_retenidos = servicio.vcpus_asignados
    ledger.ram_mb_retenida = servicio.ram_asignada_mb
    proxmox.estados[vmid] = "running"
    for r in proxmox.recursos:
        if int(r["vmid"]) == vmid:
            r["status"] = "running"
    await db.commit()
    return servicio


async def test_obtener_servicio_expone_metadatos_sin_secretos_en_claro(
    client, db, proxmox, catedra, usuario_catedra, template, auth_catedra
):
    """GET /servicios/{id} y /acceso exponen disponibilidad y metadatos tipados sin secretos."""
    servicio = await _servicio_corriendo(
        db, proxmox, catedra, usuario_catedra, template, vmid=105
    )
    servicio.acceso_metadata = {
        "metodo": "https",
        "endpoint": "https://libro.example.edu",
        "host": "libro.example.edu",
        "port": 443,
        "local_health": True,
    }
    await db.commit()

    r = await client.get(f"/servicios/{servicio.id}", headers=auth_catedra)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["disponibilidad_aplicacion"] == "utilizable"
    assert "credenciales_acceso" not in data

    r_acc = await client.get(f"/servicios/{servicio.id}/acceso", headers=auth_catedra)
    assert r_acc.status_code == 200, r_acc.text
    assert r_acc.json()["direccion"] == "https://libro.example.edu"
    assert "credenciales" not in r_acc.json()


async def test_catedra_puede_detener_e_iniciar_su_servicio(
    client, engine, db, catedra, usuario_catedra, template, auth_catedra, proxmox
):
    """La cátedra puede autogestionar el encendido y apagado de su servicio vía operaciones durables."""
    servicio = await _servicio_corriendo(
        db, proxmox, catedra, usuario_catedra, template, vmid=106
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    # Detener
    r_stop = await client.post(
        f"/servicios/{servicio.id}/stop",
        headers=auth_catedra | {"Idempotency-Key": f"stop-{uuid4()}"},
        json={},
    )
    assert r_stop.status_code == 202, r_stop.text
    await procesar_una(sessions, pve=proxmox)
    await db.refresh(servicio)
    assert servicio.estado == EstadoServicio.STOPPED

    # Iniciar
    r_start = await client.post(
        f"/servicios/{servicio.id}/start",
        headers=auth_catedra | {"Idempotency-Key": f"start-{uuid4()}"},
        json={},
    )
    assert r_start.status_code == 202, r_start.text
    await procesar_una(sessions, pve=proxmox)
    await db.refresh(servicio)
    assert servicio.estado == EstadoServicio.RUNNING


async def test_catedra_reboot_alias(
    client, engine, db, catedra, usuario_catedra, template, auth_catedra, proxmox
):
    """El alias /reboot encola y ejecuta el reinicio del servicio."""
    servicio = await _servicio_corriendo(
        db, proxmox, catedra, usuario_catedra, template, vmid=107
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    r = await client.post(
        f"/servicios/{servicio.id}/reboot",
        headers=auth_catedra | {"Idempotency-Key": f"reboot-{uuid4()}"},
        json={},
    )
    assert r.status_code == 202, r.text
    await procesar_una(sessions, pve=proxmox)
    await db.refresh(servicio)
    assert servicio.estado == EstadoServicio.RUNNING


async def test_aislamiento_multicatedra_en_servicios(
    client, db, proxmox, catedra, usuario_catedra, template, auth_catedra
):
    """Una cátedra ajena no puede detener ni ver el servicio de otra cátedra."""
    usuario_b = await factories.crear_usuario(db, username="profe_b", rol=RolUsuario.CATEDRA_ADMIN)
    await factories.crear_catedra(db, nombre="Cátedra B", titular_id=usuario_b.id)

    servicio_a = await _servicio_corriendo(
        db, proxmox, catedra, usuario_catedra, template, vmid=108
    )

    auth_b = await headers_para(db, usuario_b)

    r_get = await client.get(f"/servicios/{servicio_a.id}", headers=auth_b)
    assert r_get.status_code == 403

    r_stop = await client.post(
        f"/servicios/{servicio_a.id}/stop",
        headers=auth_b | {"Idempotency-Key": f"stop-ajeno-{uuid4()}"},
        json={},
    )
    assert r_stop.status_code == 403


async def test_metricas_servicio_proxy(
    client, db, catedra, usuario_catedra, template, auth_catedra, proxmox
):
    """GET /servicios/{id}/metricas devuelve snapshot de métricas."""
    servicio = await _servicio_corriendo(
        db, proxmox, catedra, usuario_catedra, template, vmid=109
    )

    r = await client.get(f"/servicios/{servicio.id}/metricas", headers=auth_catedra)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "cpu_usage_percent" in data
    assert "ram_usage_mb" in data
    assert "disk_usage_gb" in data
