import pytest
from app.models.servicio import EstadoServicio, Servicio
from app.models.usuario import RolUsuario
from tests.auth_helpers import headers_para
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



async def test_obtener_servicio_expone_accesos(
    client, db, catedra, usuario_catedra, template, auth_catedra
):
    """GET /servicios/{id} expone url_acceso y credenciales_acceso para compartir con alumnos."""
    servicio = await factories.crear_servicio(
        db,
        catedra_id=catedra.id,
        template_id=template.id,
        proxmox_vmid="105",
        proxmox_node="pve1",
    )
    servicio.url_acceso = "http://cat1-svc1.utn.local"
    servicio.credenciales_acceso = "Usuario: catedra1 / Red institucional"
    await db.commit()

    r = await client.get(f"/servicios/{servicio.id}", headers=auth_catedra)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["url_acceso"] == "http://cat1-svc1.utn.local"
    assert data["credenciales_acceso"] == "Usuario: catedra1 / Red institucional"


async def test_catedra_puede_detener_e_iniciar_su_servicio(
    client, db, catedra, usuario_catedra, template, auth_catedra, proxmox
):
    """La cátedra puede autogestionar el encendido y apagado de su servicio."""
    servicio = await factories.crear_servicio(
        db,
        catedra_id=catedra.id,
        template_id=template.id,
        estado=EstadoServicio.RUNNING,
        proxmox_vmid="106",
        proxmox_node="pve1",
    )
    proxmox.estados[106] = "running"

    # Detener
    r_stop = await client.post(f"/servicios/{servicio.id}/stop", headers=auth_catedra)
    assert r_stop.status_code == 200, r_stop.text
    assert r_stop.json()["estado"] == "stopped"

    # Iniciar
    r_start = await client.post(f"/servicios/{servicio.id}/start", headers=auth_catedra)
    assert r_start.status_code == 200, r_start.text
    assert r_start.json()["estado"] == "running"


async def test_catedra_reboot_alias(
    client, db, catedra, usuario_catedra, template, auth_catedra, proxmox
):
    """El alias /reboot reinicia el servicio."""
    servicio = await factories.crear_servicio(
        db,
        catedra_id=catedra.id,
        template_id=template.id,
        estado=EstadoServicio.RUNNING,
        proxmox_vmid="107",
        proxmox_node="pve1",
    )
    proxmox.estados[107] = "running"

    r = await client.post(f"/servicios/{servicio.id}/reboot", headers=auth_catedra)
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "running"


async def test_aislamiento_multicatedra_en_servicios(
    client, db, catedra, usuario_catedra, template, auth_catedra
):
    """Una cátedra ajena no puede detener ni ver los accesos del servicio de otra cátedra."""
    usuario_b = await factories.crear_usuario(db, username="profe_b", rol=RolUsuario.CATEDRA_ADMIN)
    catedra_b = await factories.crear_catedra(db, nombre="Cátedra B", titular_id=usuario_b.id)

    servicio_a = await factories.crear_servicio(
        db,
        catedra_id=catedra.id,
        template_id=template.id,
        proxmox_vmid="108",
        proxmox_node="pve1",
    )

    auth_b = await headers_para(db, usuario_b)

    # Usuario B intenta acceder al servicio de A
    r_get = await client.get(f"/servicios/{servicio_a.id}", headers=auth_b)
    assert r_get.status_code == 403

    r_stop = await client.post(f"/servicios/{servicio_a.id}/stop", headers=auth_b)
    assert r_stop.status_code == 403


async def test_metricas_servicio_proxy(
    client, db, catedra, usuario_catedra, template, auth_catedra, proxmox
):
    """GET /servicios/{id}/metricas devuelve snapshot de métricas."""
    servicio = await factories.crear_servicio(
        db,
        catedra_id=catedra.id,
        template_id=template.id,
        estado=EstadoServicio.RUNNING,
        proxmox_vmid="109",
        proxmox_node="pve1",
    )
    proxmox.estados[109] = "running"

    r = await client.get(f"/servicios/{servicio.id}/metricas", headers=auth_catedra)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "cpu_usage_percent" in data
    assert "ram_usage_mb" in data
    assert "disk_usage_gb" in data
