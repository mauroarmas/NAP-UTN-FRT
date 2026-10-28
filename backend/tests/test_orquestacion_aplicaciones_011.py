"""Orchestration tests for US1 (T037, T047): verified delivery vs pull/probe failure."""
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.compromiso_capacidad import CompromisoCapacidad
from app.models.identidad_infraestructura import IdentidadInfraestructura
from app.models.operacion_infraestructura import OperacionInfraestructura
from app.models.pedido import EstadoPedido, Pedido
from app.models.servicio import Servicio
from app.services.application_verification_service import AccessObservation
from app.worker import procesar_ingesta_una, procesar_una
from tests.test_admision_aplicaciones_011 import (
    app_order,
    approve,
    perfil_capacidad,
    profile_entry,
    red_aplicaciones_011,
)
from tests.test_creacion_aplicaciones_011 import stopped_create, wake
from tests.test_entrega_aplicaciones_011 import DeliveredNode
from tests.test_ingesta_worker_011 import ConsoleNode


async def test_verified_delivery_transitions_order_and_marks_service_usable(
    db, engine, admin, app_order, proxmox
):
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await approve(db, admin, app_order, immediate=True)
    stopped_create(proxmox)
    node = DeliveredNode(app_order, sessions)
    await procesar_una(sessions, pve=proxmox, runner=node)
    db.expire_all()
    identity = await db.scalar(select(IdentidadInfraestructura))
    proxmox.estados[identity.vmid] = "running"
    await wake(db)

    async def probe(instance):
        return AccessObservation(
            instance["host"],
            instance["address"],
            instance["port"],
            instance["configuration_sha256"],
            200,
        )

    await procesar_ingesta_una(sessions, runner=node, pve=proxmox, probe=probe)
    db.expire_all()
    service = await db.scalar(select(Servicio))
    pedido = await db.get(Pedido, service.pedido_id)
    operation = await db.scalar(select(OperacionInfraestructura))
    ledger = await db.scalar(select(CompromisoCapacidad))
    assert operation.estado == "confirmada"
    assert pedido.estado == EstadoPedido.ACTIVO
    assert service.disponibilidad_aplicacion == "utilizable"
    assert ledger.estado == "materializado"


async def test_pull_failure_never_produces_false_delivery_and_transitions_to_error(
    db, engine, admin, app_order, proxmox
):
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    pedido_id = app_order.pedido.id
    await approve(db, admin, app_order, immediate=True)
    stopped_create(proxmox)
    node = ConsoleNode(app_order, sessions)
    await procesar_una(sessions, pve=proxmox, runner=node)
    node.state = "fallido"
    await wake(db)
    await procesar_ingesta_una(sessions, runner=node, pve=proxmox)
    db.expire_all()
    service = await db.scalar(select(Servicio))
    pedido = await db.get(Pedido, pedido_id)
    operation = await db.scalar(select(OperacionInfraestructura))
    assert operation.estado == "fallida"
    assert pedido.estado == EstadoPedido.ERROR
    assert service.disponibilidad_aplicacion != "utilizable"
