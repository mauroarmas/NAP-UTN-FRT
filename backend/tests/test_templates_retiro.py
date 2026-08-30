"""Retirar una plantilla del catálogo sin romper su historial.

Retirar no es borrar. La plantilla sale del catálogo —deja de ofrecerse y no se
puede pedir— pero los pedidos y servicios que la referencian tienen que seguir
resolviéndola, o el historial académico deja de ser legible (Principio V).

Buena parte del comportamiento ya existía antes de esta feature: el catálogo
filtraba por `activo` y `crear_pedido` rechazaba plantillas inactivas. Lo que
faltaba era una forma de poner ese campo en `false` desde el portal. Estas
pruebas cubren el conjunto, para que la pieza que faltaba no quede sin red.
"""

import pytest

from tests import factories


async def test_retirar_la_saca_del_catalogo(client, auth_admin, template):
    r = await client.patch(
        f"/templates/{template.id}", json={"activo": False}, headers=auth_admin
    )
    assert r.status_code == 200
    assert r.json()["activo"] is False

    listado = await client.get("/templates/", headers=auth_admin)
    assert template.id not in [t["id"] for t in listado.json()]


async def test_la_catedra_tampoco_la_ve(client, auth_admin, auth_catedra, template):
    await client.patch(
        f"/templates/{template.id}", json={"activo": False}, headers=auth_admin
    )
    listado = await client.get("/templates/", headers=auth_catedra)
    assert template.id not in [t["id"] for t in listado.json()]


async def test_no_se_puede_pedir_una_plantilla_retirada(
    client, auth_admin, auth_catedra, catedra, template
):
    """FR-005: aunque la cátedra mande el id a mano, el pedido se rechaza."""
    await client.patch(
        f"/templates/{template.id}", json={"activo": False}, headers=auth_admin
    )
    r = await client.post(
        "/pedidos/", json={"template_id": template.id}, headers=auth_catedra
    )
    assert r.status_code == 404


async def test_el_historial_la_sigue_resolviendo(client, auth_admin, template):
    """T5/FR-006: un pedido viejo que la referencia tiene que poder mostrarla."""
    await client.patch(
        f"/templates/{template.id}", json={"activo": False}, headers=auth_admin
    )
    r = await client.get(f"/templates/{template.id}", headers=auth_admin)
    assert r.status_code == 200
    assert r.json()["nombre"] == template.nombre


async def test_retirar_no_toca_los_servicios_desplegados(
    client, auth_admin, db, catedra, template
):
    servicio = await factories.crear_servicio(
        db, catedra_id=catedra.id, template_id=template.id
    )
    await client.patch(
        f"/templates/{template.id}", json={"activo": False}, headers=auth_admin
    )
    await db.refresh(servicio)
    assert servicio.deleted_at is None
    assert servicio.proxmox_vmid is not None


async def test_reactivar_la_devuelve_al_catalogo(client, auth_admin, template):
    await client.patch(
        f"/templates/{template.id}", json={"activo": False}, headers=auth_admin
    )
    r = await client.patch(
        f"/templates/{template.id}", json={"activo": True}, headers=auth_admin
    )
    assert r.status_code == 200

    listado = await client.get("/templates/", headers=auth_admin)
    assert template.id in [t["id"] for t in listado.json()]


async def test_la_catedra_no_puede_retirar(client, auth_catedra, template):
    """FR-008: retirar plantillas es exclusivo del administrador."""
    r = await client.patch(
        f"/templates/{template.id}", json={"activo": False}, headers=auth_catedra
    )
    assert r.status_code == 403


async def test_el_admin_puede_ver_las_retiradas_para_reactivarlas(
    client, auth_admin, template
):
    """Sin esto, retirar sería un camino de ida desde la interfaz.

    El catálogo por defecto oculta las retiradas —es lo que la cátedra puede
    pedir—, así que el administrador necesita una forma de volver a encontrarlas.
    """
    await client.patch(
        f"/templates/{template.id}", json={"activo": False}, headers=auth_admin
    )
    r = await client.get("/templates/?incluir_retiradas=true", headers=auth_admin)
    assert r.status_code == 200
    assert template.id in [t["id"] for t in r.json()]


async def test_la_catedra_no_puede_ver_las_retiradas(
    client, auth_admin, auth_catedra, template
):
    """El parámetro es una herramienta de administración, no un modo de catálogo."""
    await client.patch(
        f"/templates/{template.id}", json={"activo": False}, headers=auth_admin
    )
    r = await client.get("/templates/?incluir_retiradas=true", headers=auth_catedra)
    assert template.id not in [t["id"] for t in r.json()]
