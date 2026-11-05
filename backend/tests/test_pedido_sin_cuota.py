"""Creación de pedidos bajo el modelo sin techo por cátedra.

El cambio observable: ningún pedido bien formado se rechaza por consumo
acumulado. Lo que sí se sigue validando es a nombre de quién se pide y qué se
pide — el aislamiento y la validez del perfil publicado no se relajaron.
"""

from datetime import timedelta
from zoneinfo import ZoneInfo

import pytest

from app.models.pedido import EstadoPedido, TipoPedido
from app.models.usuario import RolUsuario
from app.utils.clock import clock
from tests import factories
from tests.capacity_helpers import perfil_capacidad  # noqa: F401
from tests.service_helpers import link_capacity_definition


@pytest.fixture(autouse=True)
def cluster(proxmox, perfil_capacidad):
    return proxmox


def _vigencia():
    hoy = clock.now().astimezone(ZoneInfo("America/Argentina/Tucuman")).date()
    return {
        "tipo": "personalizado",
        "desde": hoy.isoformat(),
        "hasta": (hoy + timedelta(days=30)).isoformat(),
    }


def _payload(template_id, catedra_id=None):
    body = {
        "template_id": template_id,
        "modelo_servicio": "iaas",
        "vigencia": _vigencia(),
    }
    if catedra_id is not None:
        body["catedra_id"] = catedra_id
    return body


async def test_el_consumo_acumulado_no_frena_pedidos_sucesivos(
    client, db, catedra, template, auth_catedra
):
    """Diez pedidos seguidos entran los diez.

    Bajo el modelo anterior el segundo o tercero habría chocado contra la cuota.
    Ahora la decisión es del administrador, uno por uno.
    """
    for i in range(10):
        await factories.crear_servicio(
            db,
            catedra_id=catedra.id,
            template_id=template.id,
            proxmox_vmid=str(800 + i),
            vcpus=4,
            ram_mb=4096,
            disk_gb=8,
        )

    for i in range(10):
        r = await client.post(
            "/pedidos/",
            json=_payload(template.id, catedra.id),
            headers=auth_catedra | {"Idempotency-Key": f"sucesivo-{i}"},
        )
        assert r.status_code == 201, r.text
        assert r.json()["estado"] == EstadoPedido.SOLICITADO.value


async def test_el_pedido_nace_como_alta_y_sin_reserva(
    client, db, catedra, template, auth_catedra
):
    """La reserva la crea la aprobación, no el pedido."""
    r = await client.post(
        "/pedidos/",
        json=_payload(template.id, catedra.id),
        headers=auth_catedra | {"Idempotency-Key": "alta-sin-reserva"},
    )

    assert r.status_code == 201, r.text
    assert r.json()["tipo"] == TipoPedido.ALTA.value
    assert r.json()["compromiso_capacidad"] is None


async def test_una_persona_sin_catedras_no_puede_pedir(client, db, auth_admin, template):
    """Se lo dice en lenguaje claro, en vez de fallar en el formulario."""
    from tests.auth_helpers import headers_para

    huerfano = await factories.crear_usuario(
        db, "huerfano", rol=RolUsuario.CATEDRA_ADMIN
    )
    headers = await headers_para(db, huerfano)

    r = await client.post(
        "/pedidos/",
        json=_payload(template.id),
        headers=headers | {"Idempotency-Key": "huerfano-1"},
    )

    assert r.status_code == 422, r.text
    assert "cátedra" in r.json()["detail"]["mensaje"].lower()


async def test_un_template_grande_se_puede_pedir_sin_bloqueo(
    client, db, catedra, admin, auth_catedra
):
    grande = await factories.crear_template(
        db, nombre="LXC Grande", disk_gb=64
    )
    await link_capacity_definition(db, grande, admin)

    r = await client.post(
        "/pedidos/",
        json=_payload(grande.id, catedra.id),
        headers=auth_catedra | {"Idempotency-Key": "grande-1"},
    )

    assert r.status_code == 201, r.text


async def test_no_se_pide_sobre_un_template_inactivo(
    client, db, catedra, template, auth_catedra
):
    template.activo = False
    await db.commit()

    r = await client.post(
        "/pedidos/",
        json=_payload(template.id, catedra.id),
        headers=auth_catedra | {"Idempotency-Key": "inactivo-1"},
    )

    assert r.status_code == 422, r.text
