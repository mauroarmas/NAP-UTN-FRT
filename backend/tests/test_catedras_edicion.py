"""Edición de cátedras desde el panel de administración.

Reescrito para la feature 004: la cátedra ya no tiene cuota que editar. Lo que
el administrador gestiona ahora es la titularidad y la baja, y lo que hay que
proteger es que reasignar un titular no arrastre ni pierda los recursos, que
pertenecen a la cátedra.
"""

import pytest

from app.models.servicio import EstadoServicio
from app.models.usuario import RolUsuario
from tests import factories

# Nodo con capacidad declarada: sin esto el doble de Proxmox informa capacidad
# cero y cualquier consulta de capacidad daría números degenerados.
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


async def test_admin_reasigna_el_titular(client, db, catedra, auth_admin):
    otro = await factories.crear_usuario(db, "suplente", rol=RolUsuario.CATEDRA_ADMIN)

    r = await client.patch(
        f"/catedras/{catedra.id}", json={"titular_id": otro.id}, headers=auth_admin
    )

    assert r.status_code == 200, r.text
    assert r.json()["titular"]["username"] == "suplente"


async def test_reasignar_titular_no_mueve_los_servicios(
    client, db, catedra, template, auth_admin
):
    """Los recursos pertenecen a la cátedra, no a la persona.

    Es lo que permite responder cuánto consumió una materia aunque haya cambiado
    de responsable en el medio.
    """
    servicio = await factories.crear_servicio(
        db, catedra_id=catedra.id, template_id=template.id, proxmox_vmid="160"
    )
    otro = await factories.crear_usuario(db, "nuevo_titular")

    await client.patch(
        f"/catedras/{catedra.id}", json={"titular_id": otro.id}, headers=auth_admin
    )

    await db.refresh(servicio)
    assert servicio.catedra_id == catedra.id


async def test_admin_desactiva_una_catedra_sin_servicios(
    client, db, catedra, auth_admin
):
    r = await client.patch(
        f"/catedras/{catedra.id}", json={"activa": False}, headers=auth_admin
    )

    assert r.status_code == 200, r.text
    assert r.json()["activa"] is False


async def test_desactivar_con_servicios_vigentes_exige_confirmacion(
    client, db, catedra, template, auth_admin
):
    await factories.crear_servicio(
        db,
        catedra_id=catedra.id,
        template_id=template.id,
        proxmox_vmid="161",
        estado=EstadoServicio.RUNNING,
    )

    r = await client.patch(
        f"/catedras/{catedra.id}", json={"activa": False}, headers=auth_admin
    )

    assert r.status_code == 409, r.text
    assert r.json()["detail"]["servicios_afectados"] == 1
    await db.refresh(catedra)
    assert catedra.activa is True, "sin confirmar, la baja no debe aplicarse"


async def test_desactivar_confirmado_procede(
    client, db, catedra, template, auth_admin
):
    await factories.crear_servicio(
        db,
        catedra_id=catedra.id,
        template_id=template.id,
        proxmox_vmid="162",
        estado=EstadoServicio.RUNNING,
    )

    r = await client.patch(
        f"/catedras/{catedra.id}?confirmar=true",
        json={"activa": False},
        headers=auth_admin,
    )

    assert r.status_code == 200, r.text
    assert r.json()["activa"] is False


async def test_la_catedra_no_puede_editarse_a_si_misma(client, catedra, auth_catedra):
    r = await client.patch(
        f"/catedras/{catedra.id}", json={"nombre": "Renombrada"}, headers=auth_catedra
    )

    assert r.status_code == 403, r.text


async def test_dos_titulares_pueden_tener_catedras_homonimas(client, db, auth_admin):
    """El nombre dejó de ser único a nivel global."""
    uno = await factories.crear_usuario(db, "profe_uno")
    otro = await factories.crear_usuario(db, "profe_dos")

    primera = await client.post(
        "/catedras/",
        json={"nombre": "Programación I", "titular_id": uno.id},
        headers=auth_admin,
    )
    segunda = await client.post(
        "/catedras/",
        json={"nombre": "Programación I", "titular_id": otro.id},
        headers=auth_admin,
    )

    assert primera.status_code == 201, primera.text
    assert segunda.status_code == 201, segunda.text


async def test_el_mismo_titular_no_repite_nombre_de_catedra(client, db, auth_admin):
    uno = await factories.crear_usuario(db, "profe_repetido")

    await client.post(
        "/catedras/",
        json={"nombre": "Bases de Datos", "titular_id": uno.id},
        headers=auth_admin,
    )
    duplicada = await client.post(
        "/catedras/",
        json={"nombre": "Bases de Datos", "titular_id": uno.id},
        headers=auth_admin,
    )

    assert duplicada.status_code == 400, duplicada.text


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
