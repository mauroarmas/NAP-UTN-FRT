"""Pruebas iniciales de contrato para la feature 007: Solicitud y Aprovisionamiento IaaS/PaaS/SaaS."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pedido import EstadoPedido
from tests import factories


@pytest.mark.asyncio
async def test_smoke_endpoints_pedidos_existentes(
    client: AsyncClient,
    catedra,
    auth_catedra: dict,
    template,
):
    """Verifica que el endpoint base de pedidos responde para cátedra autenticada."""
    resp = await client.get("/pedidos/", headers=auth_catedra)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
