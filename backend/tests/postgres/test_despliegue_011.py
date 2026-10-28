"""Pruebas concurrentes en PostgreSQL para despliegue (US3 - T066):
- Dos aprobaciones sobre capacidad compartida (una sola reserva)
- Oferta cambiada durante evaluación (409)
- Dos admisiones de despliegue concurrentes (una sola operación)
- Renovación que conserva snapshot y genera una única reserva efectiva
"""
import asyncio
from copy import deepcopy
from uuid import uuid4

from fastapi import HTTPException
import pytest
from sqlalchemy import select, func

from app.models.compromiso_capacidad import CompromisoCapacidad
from app.models.operacion_infraestructura import OperacionInfraestructura
from app.models.pedido import EstadoPedido, ModeloServicio, TipoPedido
from app.models.servicio import Servicio, EstadoServicio
from app.models.vigencia import VigenciaAutorizada
from app.services import evaluacion_service, admision_service
from app.utils.clock import clock
from tests import factories
from tests.test_admision_aplicaciones_011 import app_order, approve
from tests.capacity_helpers import perfil_capacidad, seleccion
from tests.test_reserva_red_aplicacion_011 import red_aplicaciones_011
from infra.applications.tests.conftest import profile_entry


async def test_dos_aprobaciones_capacidad_compartida_una_sola_reserva(
    db, pg_sessions, admin, app_order, proxmox, catedra, usuario_catedra
):
    app = app_order
    proxmox.nodos[0]["maxcpu"] = 3  # Solo permite un Medium (2 vCPUs)
    other = await factories.crear_pedido(
        db,
        catedra.id,
        usuario_catedra.id,
        app.template.id,
        estado=EstadoPedido.SOLICITADO,
        modelo_servicio=ModeloServicio.SAAS,
    )
    ids = [app.pedido.id, other.id]
    evaluations = [
        await evaluacion_service.evaluar(db, pid, actor=admin, payload=app.body)
        for pid in ids
    ]
    await db.commit()

    barrier = asyncio.Barrier(2)

    async def decide(index):
        async with pg_sessions() as session:
            await barrier.wait()
            try:
                result = await admision_service.aprobar(
                    session,
                    ids[index],
                    actor=admin,
                    payload={
                        **app.body,
                        "capacidad_token": evaluations[index]["capacidad_token"],
                    },
                    clave=f"race-capacidad-{index}",
                )
                await session.commit()
                return result.status_code
            except HTTPException as error:
                await session.rollback()
                return error.status_code

    results = await asyncio.wait_for(
        asyncio.gather(decide(0), decide(1)), timeout=15
    )
    assert sorted(results) == [200, 409]
    assert (
        await db.scalar(select(func.count()).select_from(CompromisoCapacidad))
        == 1
    )
    assert not proxmox.creados


async def test_oferta_cambiada_durante_evaluacion_rechaza_aprobacion(
    db, admin, app_order
):
    app = app_order
    evaluation = await evaluacion_service.evaluar(
        db, app.pedido.id, actor=admin, payload=app.body
    )
    # Cambiar la revisión del template
    app.template.revision += 1
    await db.commit()

    with pytest.raises(HTTPException) as exc_info:
        await admision_service.aprobar(
            db,
            app.pedido.id,
            actor=admin,
            payload={
                **app.body,
                "capacidad_token": evaluation["capacidad_token"],
            },
            clave="test-oferta-cambiada",
        )
    assert exc_info.value.status_code == 409


async def test_dos_admisiones_despliegue_concurrentes_mismo_pedido(
    db, pg_sessions, admin, app_order, proxmox
):
    app = app_order
    # Primero se aprueba el pedido
    await approve(db, admin, app)

    barrier = asyncio.Barrier(2)

    async def deploy_call(index):
        async with pg_sessions() as session:
            await barrier.wait()
            try:
                result = await admision_service.desplegar(
                    session,
                    app.pedido.id,
                    actor=admin,
                    clave=f"deploy-race-{index}",
                )
                await session.commit()
                return result.status_code
            except HTTPException as error:
                await session.rollback()
                return error.status_code

    results = await asyncio.wait_for(
        asyncio.gather(deploy_call(0), deploy_call(1)), timeout=15
    )
    assert sorted(results) == [202, 409]
    assert (
        await db.scalar(
            select(func.count()).select_from(OperacionInfraestructura)
        )
        == 1
    )


async def test_renovacion_conserva_snapshot_y_una_unica_reserva(
    db, admin, app_order, catedra, usuario_catedra
):
    app = app_order
    await approve(db, admin, app)
    # Simular servicio activo creado
    servicio = await factories.crear_servicio(
        db,
        catedra_id=catedra.id,
        template_id=app.template.id,
        pedido_id=app.pedido.id,
        estado=EstadoServicio.RUNNING,
        vcpus=app.pedido.asignacion_snapshot["vcpus"],
        ram_mb=app.pedido.asignacion_snapshot["ram_mb"],
        disk_gb=app.pedido.asignacion_snapshot["disk_gb"],
    )
    servicio.modelo_servicio = app.pedido.modelo_servicio.value
    servicio.nombre_snapshot = "Servicio Existente"
    servicio.asignacion_snapshot = deepcopy(app.pedido.asignacion_snapshot)
    servicio.configuracion_despliegue_id = app.config.id
    # Vincular compromiso y vigencia existentes al servicio
    commitment = await db.scalar(select(CompromisoCapacidad).where(CompromisoCapacidad.pedido_id == app.pedido.id))
    commitment.servicio_id = servicio.id
    vigencia = await db.scalar(select(VigenciaAutorizada).where(VigenciaAutorizada.pedido_id == app.pedido.id))
    vigencia.servicio_id = servicio.id
    await db.commit()

    # Pedido de renovación vinculado con vigencia contigua posterior
    pedido_renov = await factories.crear_pedido(
        db,
        catedra.id,
        usuario_catedra.id,
        app.template.id,
        estado=EstadoPedido.SOLICITADO,
        modelo_servicio=app.pedido.modelo_servicio,
    )
    pedido_renov.tipo = TipoPedido.RENOVACION
    pedido_renov.servicio_id = servicio.id
    await db.commit()

    body_renov = deepcopy(app.body)
    body_renov["vigencia"] = {
        "tipo": "personalizado",
        "desde": "2026-11-28",
        "hasta": "2026-12-27",
    }

    # Evaluar renovación
    eval_renov = await evaluacion_service.evaluar(
        db, pedido_renov.id, actor=admin, payload=body_renov
    )
    # Aprobar renovación
    result = await admision_service.aprobar(
        db,
        pedido_renov.id,
        actor=admin,
        payload={
            **body_renov,
            "capacidad_token": eval_renov["capacidad_token"],
        },
        clave="approve-renewal-1",
    )
    await db.commit()

    assert result.status_code == 200
    # Renovación conserva asignación
    assert (
        pedido_renov.asignacion_snapshot["configuracion_sha256"]
        == servicio.asignacion_snapshot["configuracion_sha256"]
    )
    # Compromiso original sigue siendo 1 (renovación no duplica compromiso de capacidad)
    assert (
        await db.scalar(
            select(func.count()).select_from(CompromisoCapacidad)
        )
        == 1
    )
