"""Edición de cuotas de cátedra desde el panel de administración."""

import pytest

from app.models.servicio import EstadoServicio
from tests import factories

# Nodo con capacidad declarada: sin esto el doble de Proxmox informa capacidad
# cero y toda cuota se rechazaría por exceder el clúster.
NODO_CON_CAPACIDAD = [
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
def cluster_con_capacidad(proxmox):
    proxmox.nodos = NODO_CON_CAPACIDAD
    return proxmox


async def test_admin_edita_las_cuotas_de_una_catedra(client, db, catedra, auth_admin):
    r = await client.patch(
        f"/catedras/{catedra.id}",
        json={"cuota_vcpus": 6, "cuota_ram_mb": 2048, "cuota_storage_gb": 12},
        headers=auth_admin,
    )

    assert r.status_code == 200, r.text
    assert r.json()["cuota_vcpus"] == 6
    await db.refresh(catedra)
    assert catedra.cuota_ram_mb == 2048
    assert catedra.cuota_storage_gb == 12


async def test_admin_desactiva_una_catedra(client, db, catedra, auth_admin):
    r = await client.patch(f"/catedras/{catedra.id}", json={"activa": False}, headers=auth_admin)

    assert r.status_code == 200, r.text
    assert r.json()["activa"] is False


async def test_la_catedra_no_puede_editarse_a_si_misma(client, catedra, auth_catedra):
    r = await client.patch(
        f"/catedras/{catedra.id}", json={"cuota_vcpus": 99}, headers=auth_catedra
    )

    assert r.status_code == 403, r.text


# --- La cuota no puede quedar por debajo de lo que ya está en uso ---


async def test_no_se_puede_bajar_la_cuota_por_debajo_del_uso(
    client, db, catedra, template, auth_admin
):
    await factories.crear_servicio(
        db,
        catedra_id=catedra.id,
        template_id=template.id,
        estado=EstadoServicio.RUNNING,
        vcpus=2,
        ram_mb=1024,
        disk_gb=8,
    )

    r = await client.patch(
        f"/catedras/{catedra.id}", json={"cuota_storage_gb": 4}, headers=auth_admin
    )

    assert r.status_code == 400, r.text
    assert "en uso" in r.json()["detail"]
    await db.refresh(catedra)
    assert catedra.cuota_storage_gb == 16


async def test_bajar_la_cuota_hasta_el_uso_exacto_es_valido(
    client, db, catedra, template, auth_admin
):
    await factories.crear_servicio(
        db,
        catedra_id=catedra.id,
        template_id=template.id,
        estado=EstadoServicio.RUNNING,
        vcpus=2,
        ram_mb=1024,
        disk_gb=8,
    )

    r = await client.patch(
        f"/catedras/{catedra.id}",
        json={"cuota_vcpus": 2, "cuota_ram_mb": 1024, "cuota_storage_gb": 8},
        headers=auth_admin,
    )

    assert r.status_code == 200, r.text


async def test_los_servicios_detenidos_no_frenan_la_baja_de_cuota(
    client, db, catedra, template, auth_admin
):
    """Solo lo que está corriendo cuenta como uso, igual que en el panel de la cátedra."""
    await factories.crear_servicio(
        db,
        catedra_id=catedra.id,
        template_id=template.id,
        estado=EstadoServicio.STOPPED,
        vcpus=2,
        ram_mb=1024,
        disk_gb=8,
    )

    r = await client.patch(
        f"/catedras/{catedra.id}", json={"cuota_storage_gb": 2}, headers=auth_admin
    )

    assert r.status_code == 200, r.text


# --- Storages del clúster (desglose del dashboard) ---


async def test_storage_expone_el_espacio_de_cada_storage(client, proxmox, auth_admin):
    proxmox.recursos = [
        {
            "type": "storage",
            "storage": "local",
            "node": "pve1",
            "plugintype": "dir",
            "content": "vztmpl,iso,backup",
            "status": "available",
            "shared": 0,
            "disk": 4_648_771_584,
            "maxdisk": 14_484_905_984,
        },
        {
            "type": "storage",
            "storage": "local-lvm",
            "node": "pve1",
            "plugintype": "lvmthin",
            "content": "rootdir,images",
            "status": "available",
            "shared": 0,
            "disk": 788_396_611,
            "maxdisk": 12_675_186_688,
        },
    ]

    r = await client.get("/proxmox/storage", headers=auth_admin)

    assert r.status_code == 200, r.text
    por_nombre = {s["storage"]: s for s in r.json()}
    assert por_nombre["local"]["total_bytes"] == 14_484_905_984
    # Solo el storage con rootdir/images limita el despliegue de contenedores
    assert por_nombre["local"]["aloja_contenedores"] is False
    assert por_nombre["local-lvm"]["aloja_contenedores"] is True


async def test_storage_es_solo_para_admin(client, auth_catedra):
    r = await client.get("/proxmox/storage", headers=auth_catedra)

    assert r.status_code == 403, r.text
