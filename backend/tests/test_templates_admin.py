"""Pruebas para la administración de plantillas de recursos (US5)."""

import pytest
import pytest_asyncio

from app.models.pedido import ModeloServicio
from tests import factories
from tests.service_helpers import link_capacity_definition


@pytest_asyncio.fixture(autouse=True)
async def _definiciones_publicadas(db, template, admin):
    await link_capacity_definition(db, template, admin, product="linux")
    return template


async def test_admin_crear_template_iaas_exitoso(client, auth_admin, template):
    """Admin crea un template IaaS vinculado a definición publicada."""
    payload = {
        "nombre": "Template Test IaaS",
        "descripcion": "Instancia para pruebas",
        "modelo_servicio": "iaas",
        "tipo": "lxc",
        "default_vcpus": 2,
        "default_ram_mb": 1024,
        "default_disk_gb": 4,
        "definicion_version_id": str(template.definicion_version_id),
    }
    res = await client.post("/templates/", json=payload, headers=auth_admin)
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["nombre"] == "Template Test IaaS"
    assert data["modelo_servicio"] == "iaas"
    assert data["default_disk_gb"] == 4
    assert data["activo"] is True


async def test_crear_template_disco_grande_exitoso(client, auth_admin, template):
    """Creación de template con disco grande se acepta normalmente."""
    payload = {
        "nombre": "Template IaaS Gigante",
        "modelo_servicio": "iaas",
        "tipo": "lxc",
        "default_vcpus": 4,
        "default_ram_mb": 4096,
        "default_disk_gb": 16,
        "definicion_version_id": str(template.definicion_version_id),
    }
    res = await client.post("/templates/", json=payload, headers=auth_admin)
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["default_disk_gb"] == 16


async def test_actualizar_template_disco_grande_exitoso(client, auth_admin, template):
    """Al editar una plantilla con disco mayor a 8 GB se actualiza correctamente sin restricciones."""
    res = await client.patch(
        f"/templates/{template.id}",
        json={
            "default_disk_gb": 20,
        },
        headers=auth_admin,
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["default_disk_gb"] == 20


async def test_crear_template_paas_y_saas(client, db, auth_admin, admin):
    """Admin puede dar de alta templates con modelo PaaS y SaaS."""
    aux_paas = await factories.crear_template(db, nombre="Aux PaaS", modelo_servicio=ModeloServicio.PAAS)
    await link_capacity_definition(db, aux_paas, admin, product="postgresql")
    aux_saas = await factories.crear_template(db, nombre="Aux SaaS", modelo_servicio=ModeloServicio.SAAS)
    await link_capacity_definition(db, aux_saas, admin, product="bookstack")

    paas_res = await client.post(
        "/templates/",
        json={
            "nombre": "Template PaaS API",
            "modelo_servicio": "paas",
            "tipo": "lxc",
            "default_vcpus": 2,
            "default_ram_mb": 2048,
            "default_disk_gb": 4,
            "definicion_version_id": str(aux_paas.definicion_version_id),
        },
        headers=auth_admin,
    )
    assert paas_res.status_code == 201, paas_res.text
    assert paas_res.json()["modelo_servicio"] == "paas"

    saas_res = await client.post(
        "/templates/",
        json={
            "nombre": "Template SaaS App",
            "modelo_servicio": "saas",
            "tipo": "lxc",
            "default_vcpus": 1,
            "default_ram_mb": 1024,
            "default_disk_gb": 4,
            "definicion_version_id": str(aux_saas.definicion_version_id),
        },
        headers=auth_admin,
    )
    assert saas_res.status_code == 201, saas_res.text
    assert saas_res.json()["modelo_servicio"] == "saas"


async def test_listar_templates_filtrado_por_modelo_servicio(client, auth_admin, db, admin):
    """Filtrar el catálogo por modelo de servicio (iaas, paas, saas)."""
    t_iaas = await factories.crear_template(db, nombre="Template IaaS Único", modelo_servicio=ModeloServicio.IAAS)
    await link_capacity_definition(db, t_iaas, admin, product="linux")
    t_paas = await factories.crear_template(db, nombre="Template PaaS Único", modelo_servicio=ModeloServicio.PAAS)
    await link_capacity_definition(db, t_paas, admin, product="postgresql")
    t_saas = await factories.crear_template(db, nombre="Template SaaS Único", modelo_servicio=ModeloServicio.SAAS)
    await link_capacity_definition(db, t_saas, admin, product="bookstack")

    # Filtrar PaaS
    res_paas = await client.get("/templates/?modelo_servicio=paas", headers=auth_admin)
    assert res_paas.status_code == 200
    nombres_paas = [t["nombre"] for t in res_paas.json()]
    assert "Template PaaS Único" in nombres_paas
    assert "Template IaaS Único" not in nombres_paas
    assert "Template SaaS Único" not in nombres_paas

    # Filtrar SaaS
    res_saas = await client.get("/templates/?modelo_servicio=saas", headers=auth_admin)
    assert res_saas.status_code == 200
    nombres_saas = [t["nombre"] for t in res_saas.json()]
    assert "Template SaaS Único" in nombres_saas
    assert "Template IaaS Único" not in nombres_saas

    # Filtrar IaaS
    res_iaas = await client.get("/templates/?modelo_servicio=iaas", headers=auth_admin)
    assert res_iaas.status_code == 200
    nombres_iaas = [t["nombre"] for t in res_iaas.json()]
    assert "Template IaaS Único" in nombres_iaas
    assert "Template PaaS Único" not in nombres_iaas


async def test_desactivar_template_soft_delete(client, auth_admin, template):
    """DELETE /templates/{id} retira lógicamente la plantilla del catálogo."""
    res_del = await client.delete(f"/templates/{template.id}", headers=auth_admin)
    assert res_del.status_code == 200
    assert res_del.json()["activo"] is False

    # No debe aparecer en el catálogo regular
    res_list = await client.get("/templates/", headers=auth_admin)
    assert template.id not in [t["id"] for t in res_list.json()]

    # Sí debe aparecer con incluir_retiradas=True
    res_todas = await client.get("/templates/?incluir_retiradas=true", headers=auth_admin)
    assert template.id in [t["id"] for t in res_todas.json()]


async def test_no_admin_no_puede_gestionar_templates(client, auth_catedra, template):
    """Un usuario común o docente no puede crear, editar ni borrar plantillas."""
    # Crear
    res_crear = await client.post(
        "/templates/",
        json={"nombre": "Template No Autorizado", "tipo": "lxc"},
        headers=auth_catedra,
    )
    assert res_crear.status_code == 403

    # Editar
    res_edit = await client.patch(
        f"/templates/{template.id}",
        json={"nombre": "Nuevo Nombre"},
        headers=auth_catedra,
    )
    assert res_edit.status_code == 403

    # Borrar
    res_del = await client.delete(f"/templates/{template.id}", headers=auth_catedra)
    assert res_del.status_code == 403
