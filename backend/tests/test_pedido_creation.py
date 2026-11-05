"""Pruebas para Solicitud de Recursos IaaS, PaaS y SaaS con Vigencia explícita y perfiles."""

from datetime import timedelta
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pedido import EstadoPedido, ModeloServicio
from app.models.recurso_template import TipoRecurso
from app.utils.clock import clock
from tests import factories
from tests.capacity_helpers import perfil_capacidad  # noqa: F401
from tests.service_helpers import link_capacity_definition


def _vigencia():
    hoy = clock.now().astimezone(ZoneInfo("America/Argentina/Tucuman")).date()
    return {
        "tipo": "personalizado",
        "desde": hoy.isoformat(),
        "hasta": (hoy + timedelta(days=30)).isoformat(),
    }


@pytest.mark.asyncio
async def test_crear_pedido_iaas_exitoso(
    client: AsyncClient,
    catedra,
    auth_catedra: dict,
    template,
    perfil_capacidad,
):
    """Cátedra solicita IaaS seleccionando plantilla publicada y vigencia explícita."""
    payload = {
        "modelo_servicio": "iaas",
        "template_id": template.id,
        "vigencia": _vigencia(),
        "catedra_id": catedra.id,
    }
    resp = await client.post(
        "/pedidos/",
        json=payload,
        headers=auth_catedra | {"Idempotency-Key": "iaas-ok"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["modelo_servicio"] == "iaas"
    assert data["template_id"] == template.id
    assert data["vigencia_tipo"] == "personalizado"
    assert data["estado"] == EstadoPedido.SOLICITADO.value


@pytest.mark.asyncio
async def test_crear_pedido_iaas_sin_template_falla(
    client: AsyncClient,
    catedra,
    auth_catedra: dict,
    perfil_capacidad,
):
    """IaaS exige seleccionar plantilla de recursos."""
    payload = {
        "modelo_servicio": "iaas",
        "template_id": None,
        "vigencia": _vigencia(),
        "catedra_id": catedra.id,
    }
    resp = await client.post(
        "/pedidos/",
        json=payload,
        headers=auth_catedra | {"Idempotency-Key": "iaas-no-tpl"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_crear_pedido_saas_con_perfil_y_descripcion(
    client: AsyncClient,
    db: AsyncSession,
    catedra,
    admin,
    auth_catedra: dict,
    perfil_capacidad,
):
    """Cátedra solicita SaaS sobre un perfil publicado describiendo el libro virtual requerido."""
    saas_tpl = await factories.crear_template(
        db,
        nombre="BookStack Cátedra",
        tipo=TipoRecurso.LXC,
        modelo_servicio=ModeloServicio.SAAS,
        vcpus=2,
        ram_mb=2048,
        disk_gb=8,
    )
    await link_capacity_definition(db, saas_tpl, admin, product="bookstack")

    payload = {
        "modelo_servicio": "saas",
        "template_id": saas_tpl.id,
        "descripcion_requerimientos": "Instancia de BookStack para apuntes interactivos de cátedra",
        "vigencia": _vigencia(),
        "catedra_id": catedra.id,
    }
    resp = await client.post(
        "/pedidos/",
        json=payload,
        headers=auth_catedra | {"Idempotency-Key": "saas-ok"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["modelo_servicio"] == "saas"
    assert data["template_id"] == saas_tpl.id
    assert "BookStack" in data["descripcion_requerimientos"]
    assert data["estado"] == EstadoPedido.SOLICITADO.value


@pytest.mark.asyncio
async def test_crear_pedido_saas_sin_template_falla(
    client: AsyncClient,
    catedra,
    auth_catedra: dict,
    perfil_capacidad,
):
    """Una solicitud fuera de catálogo exige identificar el servicio requerido."""
    payload = {
        "modelo_servicio": "saas",
        "descripcion_requerimientos": "Solicitud libre sin perfil",
        "vigencia": _vigencia(),
        "catedra_id": catedra.id,
    }
    resp = await client.post(
        "/pedidos/",
        json=payload,
        headers=auth_catedra | {"Idempotency-Key": "saas-sin-tpl"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_crear_pedido_modelo_invalido_falla(
    client: AsyncClient,
    catedra,
    auth_catedra: dict,
    template,
    perfil_capacidad,
):
    """Modelo de servicio no contemplado en NIST/sistema se rechaza."""
    payload = {
        "modelo_servicio": "servidor_fisico_invalido",
        "template_id": template.id,
        "vigencia": _vigencia(),
        "catedra_id": catedra.id,
    }
    resp = await client.post(
        "/pedidos/",
        json=payload,
        headers=auth_catedra | {"Idempotency-Key": "modelo-invalido"},
    )
    assert resp.status_code == 422

