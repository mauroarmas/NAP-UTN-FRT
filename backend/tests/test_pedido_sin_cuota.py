"""Creación de pedidos bajo el modelo sin techo por cátedra.

El cambio observable: ningún pedido bien formado se rechaza por consumo
acumulado. Lo que sí se sigue validando es a nombre de quién se pide y qué se
pide — el aislamiento y los límites por recurso individual no se relajaron.
"""

import pytest

from app.models.pedido import EstadoPedido, TipoPedido
from app.models.usuario import RolUsuario
from tests import factories

NODO = [
    {
        "node": "pve1",
        "status": "online",
        "cpu": 0.1,
        "maxcpu": 16,
        "maxmem": 32 * 1024**3,
        "maxdisk": 200 * 1024**3,
    }
]


@pytest.fixture(autouse=True)
def cluster(proxmox):
    proxmox.nodos = NODO
    return proxmox


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

    for _ in range(10):
        r = await client.post(
            "/pedidos/", json={"template_id": template.id}, headers=auth_catedra
        )
        assert r.status_code == 201, r.text
        assert r.json()["estado"] == EstadoPedido.SOLICITADO.value


async def test_el_pedido_nace_como_alta_y_sin_reserva(
    client, db, catedra, template, auth_catedra
):
    """La reserva la crea la aprobación, no el pedido."""
    r = await client.post(
        "/pedidos/", json={"template_id": template.id}, headers=auth_catedra
    )

    assert r.json()["tipo"] == TipoPedido.ALTA.value
    assert r.json()["reserva_vcpus"] == 0
    assert r.json()["reserva_expira_at"] is None


async def test_una_persona_sin_catedras_no_puede_pedir(client, db, auth_admin, template):
    """Se lo dice en lenguaje claro, en vez de fallar en el formulario."""
    from app.utils.security import create_access_token

    huerfano = await factories.crear_usuario(
        db, "huerfano", rol=RolUsuario.CATEDRA_ADMIN
    )
    token = create_access_token(
        {"sub": huerfano.username, "rol": huerfano.rol.value}
    )

    r = await client.post(
        "/pedidos/",
        json={"template_id": template.id},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert r.status_code == 400, r.text
    assert "cátedra" in r.json()["detail"].lower()


async def test_el_tope_de_disco_sigue_aplicando_al_pedir(
    client, db, catedra, auth_catedra, auth_admin
):
    """Quitar la cuota por cátedra no relajó el límite por contenedor.

    Es un límite por recurso individual, no un techo agregado: son cosas
    distintas y solo desapareció la segunda.
    """
    grande = await factories.crear_template(
        db, nombre="LXC Desmedido", disk_gb=64
    )

    r = await client.post(
        "/pedidos/", json={"template_id": grande.id}, headers=auth_catedra
    )

    assert r.status_code == 400, r.text
    assert "8 GB" in r.json()["detail"]


async def test_un_template_grande_justificado_si_se_puede_pedir(
    client, db, catedra, auth_catedra
):
    grande = await factories.crear_template(
        db, nombre="LXC Justificado", disk_gb=64
    )
    grande.justificacion_disco = "Dataset de la materia, aprobado por dirección"
    await db.commit()

    r = await client.post(
        "/pedidos/", json={"template_id": grande.id}, headers=auth_catedra
    )

    assert r.status_code == 201, r.text


async def test_no_se_pide_sobre_un_template_inactivo(
    client, db, catedra, template, auth_catedra
):
    template.activo = False
    await db.commit()

    r = await client.post(
        "/pedidos/", json={"template_id": template.id}, headers=auth_catedra
    )

    assert r.status_code == 404, r.text
