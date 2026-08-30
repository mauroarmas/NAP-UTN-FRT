"""Reserva de capacidad al aprobar: el corazón del modelo nuevo.

Sin reserva, el administrador puede aprobar tres pedidos seguidos viendo el
mismo saldo libre y sobrecomprometer el clúster sin cometer un solo error
individual: cada decisión sería correcta contra los números que vio. Estas
pruebas verifican que aprobar descuente en el acto.
"""

import pytest

from app.models.pedido import EstadoPedido
from app.models.servicio import EstadoServicio
from app.services import capacidad_service
from tests import factories

NODO = [
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
def cluster(proxmox):
    proxmox.nodos = NODO
    return proxmox


async def _pedido_solicitado(db, catedra, usuario, template):
    return await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario.id,
        template_id=template.id,
        estado=EstadoPedido.SOLICITADO,
    )


async def test_aprobar_reserva_capacidad_antes_de_desplegar(
    client, db, catedra, usuario_catedra, template, auth_admin
):
    """El caso que motivó todo el rediseño."""
    pedido = await _pedido_solicitado(db, catedra, usuario_catedra, template)

    antes = await capacidad_service.panorama(db)
    assert antes["reservado"]["vcpus"] == 0

    r = await client.post(f"/pedidos/{pedido.id}/aprobar", json={}, headers=auth_admin)
    assert r.status_code == 200, r.text

    despues = await capacidad_service.panorama(db)
    # Nada se desplegó todavía, pero la capacidad ya está comprometida.
    assert despues["desplegado"]["vcpus"] == antes["desplegado"]["vcpus"]
    assert despues["reservado"]["vcpus"] == template.default_vcpus
    assert despues["libre"]["vcpus"] == antes["libre"]["vcpus"] - template.default_vcpus


async def test_dos_aprobaciones_consecutivas_no_comparten_la_misma_capacidad(
    client, db, catedra, usuario_catedra, template, auth_admin
):
    """La segunda evaluación ya descuenta la primera aprobación."""
    uno = await _pedido_solicitado(db, catedra, usuario_catedra, template)
    dos = await _pedido_solicitado(db, catedra, usuario_catedra, template)

    ev_uno = await client.get(f"/pedidos/{uno.id}/evaluacion", headers=auth_admin)
    libre_inicial = ev_uno.json()["capacidad"]["libre"]["vcpus"]

    await client.post(f"/pedidos/{uno.id}/aprobar", json={}, headers=auth_admin)

    ev_dos = await client.get(f"/pedidos/{dos.id}/evaluacion", headers=auth_admin)
    libre_despues = ev_dos.json()["capacidad"]["libre"]["vcpus"]

    assert libre_despues == libre_inicial - template.default_vcpus, (
        "la evaluación del segundo pedido debe descontar el primero, "
        "aunque su servicio todavía no exista"
    )


async def test_token_desactualizado_rechaza_la_aprobacion(
    client, db, catedra, usuario_catedra, template, auth_admin
):
    """Confirmar sobre números viejos no aprueba: pide reconfirmar."""
    uno = await _pedido_solicitado(db, catedra, usuario_catedra, template)
    dos = await _pedido_solicitado(db, catedra, usuario_catedra, template)

    # El admin abre el segundo pedido y se queda con ese token...
    ev = await client.get(f"/pedidos/{dos.id}/evaluacion", headers=auth_admin)
    token_viejo = ev.json()["capacidad_token"]

    # ...pero en el medio se aprueba otro, y la capacidad cambia.
    await client.post(f"/pedidos/{uno.id}/aprobar", json={}, headers=auth_admin)

    r = await client.post(
        f"/pedidos/{dos.id}/aprobar",
        json={"capacidad_token": token_viejo},
        headers=auth_admin,
    )

    assert r.status_code == 409, r.text
    assert r.json()["detail"]["codigo"] == "token_desactualizado"
    await db.refresh(dos)
    assert dos.estado == EstadoPedido.SOLICITADO, "no debe aprobarse con datos viejos"


async def test_token_vigente_permite_aprobar(
    client, db, catedra, usuario_catedra, template, auth_admin
):
    pedido = await _pedido_solicitado(db, catedra, usuario_catedra, template)
    ev = await client.get(f"/pedidos/{pedido.id}/evaluacion", headers=auth_admin)

    r = await client.post(
        f"/pedidos/{pedido.id}/aprobar",
        json={"capacidad_token": ev.json()["capacidad_token"]},
        headers=auth_admin,
    )

    assert r.status_code == 200, r.text


async def test_exceder_capacidad_sin_justificacion_da_400(
    client, db, catedra, usuario_catedra, auth_admin
):
    """Sobrecomprometer es posible, pero nunca accidental."""
    enorme = await factories.crear_template(
        db, nombre="LXC Enorme", vcpus=64, ram_mb=64 * 1024, disk_gb=8
    )
    pedido = await _pedido_solicitado(db, catedra, usuario_catedra, enorme)

    r = await client.post(f"/pedidos/{pedido.id}/aprobar", json={}, headers=auth_admin)

    assert r.status_code == 400, r.text
    assert r.json()["detail"]["codigo"] == "excede_capacidad"


async def test_exceder_capacidad_con_justificacion_procede(
    client, db, catedra, usuario_catedra, auth_admin
):
    """La decisión es del administrador; el sistema no la bloquea."""
    enorme = await factories.crear_template(
        db, nombre="LXC Enorme", vcpus=64, ram_mb=64 * 1024, disk_gb=8
    )
    pedido = await _pedido_solicitado(db, catedra, usuario_catedra, enorme)

    r = await client.post(
        f"/pedidos/{pedido.id}/aprobar",
        json={"justificacion_capacidad": "Se apaga el laboratorio viejo esta semana"},
        headers=auth_admin,
    )

    assert r.status_code == 200, r.text
    await db.refresh(pedido)
    assert pedido.justificacion_capacidad.startswith("Se apaga")


async def test_ram_en_riesgo_suma_los_pausados(
    client, db, catedra, template, auth_admin
):
    """Anticipa qué reactivaciones van a fallar, antes de que le fallen a alguien."""
    await factories.crear_servicio(
        db,
        catedra_id=catedra.id,
        template_id=template.id,
        proxmox_vmid="170",
        estado=EstadoServicio.PAUSED,
        ram_mb=2048,
    )

    estado = await capacidad_service.panorama(db)

    assert estado["ram_en_riesgo_mb"] == 2048


async def test_el_servicio_pausado_libera_computo_pero_no_disco(
    client, db, catedra, template
):
    """Pausar detiene el contenedor: devuelve CPU y RAM, no almacenamiento."""
    await factories.crear_servicio(
        db,
        catedra_id=catedra.id,
        template_id=template.id,
        proxmox_vmid="171",
        estado=EstadoServicio.PAUSED,
        vcpus=2,
        ram_mb=1024,
        disk_gb=4,
    )

    estado = await capacidad_service.panorama(db)

    assert estado["desplegado"]["vcpus"] == 0
    assert estado["desplegado"]["ram_mb"] == 0
    assert estado["desplegado"]["storage_gb"] == 4


async def test_solo_se_aprueban_pedidos_solicitados(
    client, db, catedra, usuario_catedra, template, auth_admin
):
    pedido = await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario_catedra.id,
        template_id=template.id,
        estado=EstadoPedido.APROBADO,
    )

    r = await client.post(f"/pedidos/{pedido.id}/aprobar", json={}, headers=auth_admin)

    assert r.status_code == 409, r.text


async def test_rechazar_exige_motivo_y_la_catedra_lo_ve(
    client, db, catedra, usuario_catedra, template, auth_admin, auth_catedra
):
    pedido = await _pedido_solicitado(db, catedra, usuario_catedra, template)

    sin_motivo = await client.post(
        f"/pedidos/{pedido.id}/rechazar", json={"motivo": "  "}, headers=auth_admin
    )
    assert sin_motivo.status_code == 400

    con_motivo = await client.post(
        f"/pedidos/{pedido.id}/rechazar",
        json={"motivo": "El clúster está al límite este cuatrimestre"},
        headers=auth_admin,
    )
    assert con_motivo.status_code == 200, con_motivo.text

    visto = await client.get(f"/pedidos/{pedido.id}", headers=auth_catedra)
    assert "al límite" in visto.json()["motivo_rechazo"]
