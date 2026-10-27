"""Compuerta constitucional de la reversión: los dos lados de la atomicidad."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.compromiso_capacidad import CompromisoCapacidad
from app.models.pedido import EstadoPedido, Pedido
from app.services import capacidad_service, pedido_service
from tests import factories
from tests.capacity_helpers import aprobar_http, perfil_capacidad


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


async def test_dos_reversiones_simultaneas_liberan_una_sola_vez(
    engine, client, db, catedra, usuario_catedra, template, admin, auth_admin
):
    """FR-004, FR-005, SC-006, I1 — el escenario que puede dejar el sistema peor."""
    default_vcpus = template.default_vcpus
    pedido = await _aprobado(client, db, catedra, usuario_catedra, template, auth_admin)
    antes = await capacidad_service.panorama(db)
    await db.commit()

    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as sesion_a, Session() as sesion_b:
        assert (await sesion_a.get(Pedido, pedido.id)).estado == EstadoPedido.APROBADO
        assert (await sesion_b.get(Pedido, pedido.id)).estado == EstadoPedido.APROBADO

        await pedido_service.revertir_aprobacion(
            sesion_a, pedido.id, admin, motivo="me equivoqué de pedido", clave="rev-conc-a"
        )
        await sesion_a.commit()

        with pytest.raises(Exception) as fallo:
            await pedido_service.revertir_aprobacion(
                sesion_b, pedido.id, admin, motivo="yo también lo estaba revirtiendo", clave="rev-conc-b"
            )

    assert fallo.value.status_code == 409

    async with Session() as verificacion:
        despues = await capacidad_service.panorama(verificacion)
    assert (
        despues["libre"]["vcpus"] == antes["libre"]["vcpus"] + default_vcpus
    ), (
        "la capacidad libre debe subir exactamente una vez: si sube el doble, el "
        "administrador aprobará sobre recursos que no existen"
    )


async def test_un_fallo_a_mitad_de_camino_no_deja_nada_a_medias(
    engine, client, db, catedra, usuario_catedra, template, admin, auth_admin, monkeypatch
):
    """FR-004, P3, I3 — el camino de fallo."""
    pedido = await _aprobado(client, db, catedra, usuario_catedra, template, auth_admin)
    comprometida = await capacidad_service.panorama(db)

    async def _explota(*args, **kwargs):
        raise RuntimeError("la base se cayó justo después de liberar la reserva")

    monkeypatch.setattr(pedido_service, "transicionar", _explota)

    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as sesion:
        with pytest.raises(RuntimeError):
            await pedido_service.revertir_aprobacion(
                sesion, pedido.id, admin, motivo="esta reversión no va a terminar", clave="rev-fallo"
            )

    async with Session() as verificacion:
        quedo = await verificacion.get(Pedido, pedido.id)
        assert quedo.estado == EstadoPedido.APROBADO, "el pedido no puede quedar revertido a medias"
        ledger = await verificacion.scalar(
            select(CompromisoCapacidad).where(CompromisoCapacidad.pedido_id == pedido.id)
        )
        assert ledger.vcpus_retenidos == template.default_vcpus
        assert ledger.ram_mb_retenida == template.default_ram_mb
        assert ledger.disk_bytes_retenidos == template.default_disk_gb * 1024**3
        assert ledger.expira_at is not None

        despues = await capacidad_service.panorama(verificacion)
        assert despues["libre"] == comprometida["libre"], (
            "nunca puede haber capacidad liberada sobre un pedido que sigue aprobado (I3)"
        )
