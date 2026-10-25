"""Una sola definición de qué significa liberar una reserva (R2).

En 009, la autoridad de capacidad reside en `CompromisoCapacidad` (ledger) y
la liberación ocurre a través de `admision_service.liberar`, usada tanto por
la reversión humana como por `capacidad_service.expirar_reservas`.
"""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models.compromiso_capacidad import CompromisoCapacidad
from app.models.pedido import EstadoPedido, Pedido
from app.services import admision_service, capacidad_service
from app.utils.clock import clock
from tests import factories
from tests.capacity_helpers import aprobar_http, perfil_capacidad  # noqa:F401


@pytest.fixture(autouse=True)
def cluster(proxmox, perfil_capacidad):
    return proxmox


async def _aprobado(client, db, catedra, usuario, template, auth_admin):
    pedido = await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario.id,
        template_id=template.id,
        estado=EstadoPedido.SOLICITADO,
    )
    r = await aprobar_http(client, pedido, template, auth_admin)
    assert r.status_code == 200, r.text
    await db.refresh(pedido)
    return pedido


async def test_liberar_pone_los_tres_campos_en_cero_y_limpia_el_vencimiento(
    client, db, catedra, usuario_catedra, template, auth_admin, admin
):
    pedido = await _aprobado(client, db, catedra, usuario_catedra, template, auth_admin)
    ledger = await db.scalar(
        select(CompromisoCapacidad).where(CompromisoCapacidad.pedido_id == pedido.id)
    )
    assert ledger.vcpus_retenidos == template.default_vcpus
    assert ledger.expira_at is not None

    res = await admision_service.liberar(
        db, pedido.id, actor=admin, motivo="Reversión administrativa", clave=f"lib:{pedido.id}"
    )
    await db.commit()
    await db.refresh(ledger)

    assert (ledger.vcpus_retenidos, ledger.ram_mb_retenida, ledger.disk_bytes_retenidos) == (0, 0, 0)
    assert ledger.estado == "liberado"
    assert ledger.expira_at is None, (
        "una reserva liberada no puede seguir teniendo un vencimiento pendiente"
    )
    assert res.resultado["capacidad_liberada"] == {
        "vcpus": template.default_vcpus,
        "ram_mb": template.default_ram_mb,
        "storage_gb": template.default_disk_gb,
    }, "devuelve lo que se liberó, para poder mostrarlo sin volver a consultar"


async def test_liberar_es_idempotente_sobre_una_reserva_ya_en_cero(
    client, db, catedra, usuario_catedra, template, auth_admin, admin
):
    """Repetir la misma decisión de liberación con la misma clave devuelve replay
    sin liberar dos veces ni duplicar efectos.
    """
    pedido = await _aprobado(client, db, catedra, usuario_catedra, template, auth_admin)

    primera = await admision_service.liberar(
        db, pedido.id, actor=admin, motivo="Reversión idempotente", clave=f"idem:{pedido.id}"
    )
    await db.commit()
    segunda = await admision_service.liberar(
        db, pedido.id, actor=admin, motivo="Reversión idempotente", clave=f"idem:{pedido.id}"
    )
    await db.commit()

    assert segunda.replayed is True
    assert segunda.resultado == primera.resultado
    ledger = await db.scalar(
        select(CompromisoCapacidad).where(CompromisoCapacidad.pedido_id == pedido.id)
    )
    assert (ledger.vcpus_retenidos, ledger.ram_mb_retenida, ledger.disk_bytes_retenidos) == (0, 0, 0)


async def test_tras_liberar_el_pedido_deja_de_contar_como_reserva_vigente(
    client, db, catedra, usuario_catedra, template, auth_admin, admin
):
    """La comprobación que importa: la contabilidad deja de verlo.

    No alcanza con que los campos queden en cero; lo que se prueba es que el
    cómputo de capacidad —que es quien decide si otra cátedra puede aprobar—
    refleja la liberación.
    """
    pedido = await _aprobado(client, db, catedra, usuario_catedra, template, auth_admin)
    con_reserva = await capacidad_service.panorama(db)
    assert con_reserva["reservado"]["vcpus"] == template.default_vcpus

    await admision_service.liberar(
        db, pedido.id, actor=admin, motivo="Liberar capacidad", clave=f"pan:{pedido.id}"
    )
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
    """`expirar_reservas` delega en la misma liberación transaccional."""
    pedido = await _aprobado(client, db, catedra, usuario_catedra, template, auth_admin)
    ledger = await db.scalar(
        select(CompromisoCapacidad).where(CompromisoCapacidad.pedido_id == pedido.id)
    )
    ledger.expira_at = clock.now() - timedelta(minutes=1)
    await db.commit()

    await capacidad_service.expirar_reservas(db)

    vencido = (
        await db.execute(select(Pedido).where(Pedido.id == pedido.id))
    ).scalar_one()
    await db.refresh(ledger)
    assert vencido.estado == EstadoPedido.RECHAZADO
    assert (ledger.vcpus_retenidos, ledger.ram_mb_retenida, ledger.disk_bytes_retenidos) == (0, 0, 0)
    assert ledger.estado == "liberado"
    assert ledger.expira_at is None
