"""Una sola definición de qué significa liberar una reserva (R2).

Hasta esta feature, poner una reserva en cero era algo que solo sabía hacer el
bucle de `expirar_reservas`. La reversión humana necesita exactamente lo mismo,
y duplicar la lógica crearía dos definiciones que pueden divergir — divergir
acá significa capacidad fantasma: comprometida en la contabilidad, sin nada
detrás.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.pedido import EstadoPedido, Pedido
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


async def _aprobado(client, db, catedra, usuario, template, auth_admin):
    pedido = await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario.id,
        template_id=template.id,
        estado=EstadoPedido.SOLICITADO,
    )
    r = await client.post(f"/pedidos/{pedido.id}/aprobar", json={}, headers=auth_admin)
    assert r.status_code == 200, r.text
    await db.refresh(pedido)
    return pedido


async def test_liberar_pone_los_tres_campos_en_cero_y_limpia_el_vencimiento(
    client, db, catedra, usuario_catedra, template, auth_admin
):
    pedido = await _aprobado(client, db, catedra, usuario_catedra, template, auth_admin)
    assert pedido.reserva_vcpus == template.default_vcpus
    assert pedido.reserva_expira_at is not None

    liberado = capacidad_service.liberar_reserva(pedido)

    assert (pedido.reserva_vcpus, pedido.reserva_ram_mb, pedido.reserva_disk_gb) == (0, 0, 0)
    assert pedido.reserva_expira_at is None, (
        "una reserva liberada no puede seguir teniendo un vencimiento pendiente"
    )
    assert liberado == {
        "vcpus": template.default_vcpus,
        "ram_mb": template.default_ram_mb,
        "storage_gb": template.default_disk_gb,
    }, "devuelve lo que se liberó, para poder mostrarlo sin volver a consultar"


async def test_liberar_es_idempotente_sobre_una_reserva_ya_en_cero(
    client, db, catedra, usuario_catedra, template, auth_admin
):
    """El caso de la renovación (R7): reserva cero desde el principio.

    Una renovación aprobada no reserva nada —el servicio ya cuenta como
    consumo—, así que liberar tiene que ser una operación sin efecto, no un
    caso especial que haya que recordar esquivar.
    """
    pedido = await _aprobado(client, db, catedra, usuario_catedra, template, auth_admin)

    capacidad_service.liberar_reserva(pedido)
    segunda = capacidad_service.liberar_reserva(pedido)

    assert segunda == {"vcpus": 0, "ram_mb": 0, "storage_gb": 0}
    assert (pedido.reserva_vcpus, pedido.reserva_ram_mb, pedido.reserva_disk_gb) == (0, 0, 0)


async def test_tras_liberar_el_pedido_deja_de_contar_como_reserva_vigente(
    client, db, catedra, usuario_catedra, template, auth_admin
):
    """La comprobación que importa: la contabilidad deja de verlo.

    No alcanza con que los campos queden en cero; lo que se prueba es que el
    cómputo de capacidad —que es quien decide si otra cátedra puede aprobar—
    refleja la liberación.
    """
    pedido = await _aprobado(client, db, catedra, usuario_catedra, template, auth_admin)
    con_reserva = await capacidad_service.panorama(db)
    assert con_reserva["reservado"]["vcpus"] == template.default_vcpus

    capacidad_service.liberar_reserva(pedido)
    await db.commit()

    liberada = await capacidad_service.panorama(db)
    assert liberada["reservado"]["vcpus"] == 0
    assert (
        liberada["libre"]["vcpus"]
        == con_reserva["libre"]["vcpus"] + template.default_vcpus
    )


async def test_el_vencimiento_automatico_usa_la_misma_definicion(
    client, db, catedra, usuario_catedra, template, auth_admin
):
    """`expirar_reservas` no puede tener su propia forma de liberar.

    Si mañana alguien agrega un cuarto campo a la reserva y lo pone en cero solo
    en uno de los dos caminos, esta prueba es la que se entera.
    """
    pedido = await _aprobado(client, db, catedra, usuario_catedra, template, auth_admin)
    pedido.reserva_expira_at = datetime.utcnow() - timedelta(minutes=1)
    await db.commit()

    await capacidad_service.expirar_reservas(db)

    vencido = (
        await db.execute(select(Pedido).where(Pedido.id == pedido.id))
    ).scalar_one()
    assert (vencido.reserva_vcpus, vencido.reserva_ram_mb, vencido.reserva_disk_gb) == (0, 0, 0)
    assert vencido.reserva_expira_at is None
