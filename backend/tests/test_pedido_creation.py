"""Pruebas para User Story 1: Solicitud de Recursos IaaS, PaaS y SaaS con Vigencia."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pedido import EstadoPedido, ModeloServicio, VigenciaTipo
from tests import factories


@pytest.mark.asyncio
async def test_crear_pedido_iaas_exitoso(
    client: AsyncClient,
    catedra,
    auth_catedra: dict,
    template,
):
    """Cátedra solicita IaaS seleccionando plantilla y vigencia."""
    payload = {
        "modelo_servicio": "iaas",
        "template_id": template.id,
        "vigencia_tipo": "primer_cuatrimestre",
        "catedra_id": catedra.id,
    }
    resp = await client.post("/pedidos/", json=payload, headers=auth_catedra)
    assert resp.status_code == 201
    data = resp.json()
    assert data["modelo_servicio"] == "iaas"
    assert data["template_id"] == template.id
    assert data["vigencia_tipo"] == "primer_cuatrimestre"
    assert data["estado"] == EstadoPedido.SOLICITADO.value


@pytest.mark.asyncio
async def test_crear_pedido_iaas_sin_template_falla(
    client: AsyncClient,
    catedra,
    auth_catedra: dict,
):
    """IaaS exige seleccionar plantilla de recursos."""
    payload = {
        "modelo_servicio": "iaas",
        "template_id": None,
        "vigencia_tipo": "primer_cuatrimestre",
        "catedra_id": catedra.id,
    }
    resp = await client.post("/pedidos/", json=payload, headers=auth_catedra)
    assert resp.status_code == 400
    assert "plantilla" in resp.json()["detail"]["mensaje"].lower()


@pytest.mark.asyncio
async def test_crear_pedido_saas_con_descripcion_libre(
    client: AsyncClient,
    catedra,
    auth_catedra: dict,
):
    """Cátedra solicita SaaS describiendo el libro virtual o software requerido."""
    payload = {
        "modelo_servicio": "saas",
        "descripcion_requerimientos": "Instancia de BookStack para apuntes interactivos de cátedra",
        "vigencia_tipo": "anual",
        "catedra_id": catedra.id,
    }
    resp = await client.post("/pedidos/", json=payload, headers=auth_catedra)
    assert resp.status_code == 201
    data = resp.json()
    assert data["modelo_servicio"] == "saas"
    assert data["template_id"] is None
    assert "BookStack" in data["descripcion_requerimientos"]
    assert data["vigencia_tipo"] == "anual"
    assert data["estado"] == EstadoPedido.SOLICITADO.value


@pytest.mark.asyncio
async def test_crear_pedido_saas_sin_descripcion_falla(
    client: AsyncClient,
    catedra,
    auth_catedra: dict,
):
    """SaaS sin template exige obligatoriamente descripción de requerimientos."""
    payload = {
        "modelo_servicio": "saas",
        "descripcion_requerimientos": "",
        "vigencia_tipo": "anual",
        "catedra_id": catedra.id,
    }
    resp = await client.post("/pedidos/", json=payload, headers=auth_catedra)
    assert resp.status_code == 400
    assert "requerimientos" in resp.json()["detail"]["mensaje"].lower()


@pytest.mark.asyncio
async def test_crear_pedido_modelo_invalido_falla(
    client: AsyncClient,
    catedra,
    auth_catedra: dict,
    template,
):
    """Modelo de servicio no contemplado en NIST/sistema se rechaza."""
    payload = {
        "modelo_servicio": "servidor_fisico_invalido",
        "template_id": template.id,
        "vigencia_tipo": "primer_cuatrimestre",
        "catedra_id": catedra.id,
    }
    resp = await client.post("/pedidos/", json=payload, headers=auth_catedra)
    assert resp.status_code == 400
    assert "modelo de servicio inválido" in resp.json()["detail"]["mensaje"].lower()

