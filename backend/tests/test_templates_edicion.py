"""Corregir una plantilla ya creada.

Hasta esta feature las plantillas eran de solo lectura después del alta: una
cargada con la imagen equivocada quedaba inservible para siempre y seguía
ofreciéndose en el catálogo. Peor: fallaba tarde, después de que la cátedra
pidió y el administrador aprobó comprometiendo capacidad. La única salida era
un UPDATE por SQL, que la constitución prohíbe.

Estas pruebas cubren la edición y, sobre todo, sus límites: qué no debe cambiar
(el tipo), qué reglas se conservan (el tope de disco) y qué no debe tocarse
nunca (lo ya entregado).
"""

import pytest

from app.models.servicio import EstadoServicio
from tests import factories


async def test_corregir_la_imagen_del_sistema(client, auth_admin, template):
    """El caso que motivó la feature: la plantilla apunta a una imagen inexistente."""
    r = await client.patch(
        f"/templates/{template.id}",
        json={"os_template": "local:vztmpl/debian-13-standard_13.6-1_amd64.tar.zst"},
        headers=auth_admin,
    )
    assert r.status_code == 200
    assert r.json()["os_template"].endswith("debian-13-standard_13.6-1_amd64.tar.zst")


async def test_solo_se_aplican_los_campos_enviados(client, auth_admin, template):
    nombre_original = template.nombre
    r = await client.patch(
        f"/templates/{template.id}",
        json={"default_ram_mb": 1024},
        headers=auth_admin,
    )
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["default_ram_mb"] == 1024
    assert cuerpo["nombre"] == nombre_original, "un campo no enviado no debe cambiar"


async def test_el_tipo_no_es_editable(client, auth_admin, template):
    """T4: cambiar lxc por qemu altera la naturaleza de lo que ya se aprobó."""
    r = await client.patch(
        f"/templates/{template.id}",
        json={"tipo": "qemu"},
        headers=auth_admin,
    )
    assert r.status_code == 400
    assert "tipo" in str(r.json()["detail"]).lower()


async def test_nombre_duplicado_se_rechaza(client, auth_admin, db, template):
    """T6: la unicidad del nombre se conserva al editar."""
    otra = await factories.crear_template(db, nombre="Otra plantilla")
    r = await client.patch(
        f"/templates/{otra.id}",
        json={"nombre": template.nombre},
        headers=auth_admin,
    )
    assert r.status_code == 409


async def test_conservar_el_propio_nombre_no_es_duplicado(client, auth_admin, template):
    """T6: la comprobación debe excluir a la propia plantilla.

    Sin esta exclusión, guardar el formulario sin tocar el nombre fallaría.
    """
    r = await client.patch(
        f"/templates/{template.id}",
        json={"nombre": template.nombre, "default_vcpus": 2},
        headers=auth_admin,
    )
    assert r.status_code == 200
    assert r.json()["default_vcpus"] == 2


async def test_disco_sobre_el_tope_sin_justificacion_se_rechaza(
    client, auth_admin, template
):
    """T3/FR-007: la edición está sujeta al mismo tope que el alta."""
    r = await client.patch(
        f"/templates/{template.id}",
        json={"default_disk_gb": 32},
        headers=auth_admin,
    )
    assert r.status_code == 400


async def test_disco_sobre_el_tope_con_justificacion_se_acepta(
    client, auth_admin, template
):
    r = await client.patch(
        f"/templates/{template.id}",
        json={
            "default_disk_gb": 32,
            "justificacion_disco": "Base de datos de la cátedra de BD, acordado con el titular",
        },
        headers=auth_admin,
    )
    assert r.status_code == 200
    assert r.json()["default_disk_gb"] == 32
    assert r.json()["justificacion_disco"]


async def test_la_catedra_no_puede_editar_plantillas(client, auth_catedra, template):
    """FR-008: corregir plantillas es exclusivo del administrador."""
    r = await client.patch(
        f"/templates/{template.id}",
        json={"default_vcpus": 8},
        headers=auth_catedra,
    )
    assert r.status_code == 403


async def test_plantilla_inexistente(client, auth_admin):
    r = await client.patch(
        "/templates/99999", json={"default_vcpus": 2}, headers=auth_admin
    )
    assert r.status_code == 404


# --- T1 / FR-002: editar no toca lo ya entregado ---


async def test_editar_no_altera_un_servicio_desplegado(
    client, auth_admin, db, catedra, template
):
    """El servicio guarda sus propios recursos, fijados al desplegar."""
    servicio = await factories.crear_servicio(
        db,
        catedra_id=catedra.id,
        template_id=template.id,
        vcpus=1,
        ram_mb=256,
        disk_gb=4,
    )

    r = await client.patch(
        f"/templates/{template.id}",
        json={"default_vcpus": 8, "default_ram_mb": 8192},
        headers=auth_admin,
    )
    assert r.status_code == 200

    await db.refresh(servicio)
    assert servicio.vcpus_asignados == 1
    assert servicio.ram_asignada_mb == 256
    assert servicio.disk_asignado_gb == 4
    assert servicio.estado == EstadoServicio.RUNNING, "no debe reiniciarse ni recrearse"


async def test_la_respuesta_informa_el_alcance_del_cambio(
    client, auth_admin, db, catedra, template
):
    """FR-003: el administrador ve qué queda fuera del alcance, sin bloquearse."""
    await factories.crear_servicio(db, catedra_id=catedra.id, template_id=template.id)

    r = await client.patch(
        f"/templates/{template.id}",
        json={"default_vcpus": 2},
        headers=auth_admin,
    )
    assert r.status_code == 200
    alcance = r.json().get("alcance_del_cambio")
    assert alcance is not None
    assert alcance["servicios_desplegados"] == 1
    assert "pedidos_aprobados_pendientes" in alcance
