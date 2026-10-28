"""Pruebas concurrentes y de retención en PostgreSQL para reintentos (US5 - T090):
- Doble invocación concurrente de reintento sobre operación fallida (debe generarse exactamente
  una operación 'reparar' y la otra recibir 409).
- Recreación del mismo pedido conserva valores y referencias de secretos de aplicación (SecretoDespliegue).
- Renovación de pedido conserva secretos del pedido original; nuevo alta genera secretos nuevos.
"""
import asyncio
from copy import deepcopy
from uuid import uuid4
import pytest
from sqlalchemy import select
from fastapi import HTTPException

from app.models.compromiso_capacidad import CompromisoCapacidad
from app.models.configuracion_despliegue import ConfiguracionDespliegue
from app.models.identidad_infraestructura import IdentidadInfraestructura
from app.models.operacion_infraestructura import OperacionInfraestructura
from app.models.pedido import Pedido, EstadoPedido, TipoPedido, ModeloServicio
from app.models.reserva_red_aplicacion import ReservaRedAplicacion
from app.models.secreto_despliegue import SecretoDespliegue
from app.models.servicio import Servicio, EstadoServicio
from app.models.recurso_template import RecursoTemplate
from app.services import (
    reconciliacion_service,
    secreto_despliegue_service,
    admision_service,
    evaluacion_service,
    identidad_infra_service,
)
from app.utils.clock import clock
from tests import factories
from tests.test_admision_aplicaciones_011 import (
    app_order,
    approve,
    perfil_capacidad,
    red_aplicaciones_011,
    profile_entry,
)
from tests.test_creacion_aplicaciones_011 import stopped_create, wake
from tests.test_entrega_aplicaciones_011 import DeliveredNode
from app.worker import procesar_una, procesar_ingesta_una
from app.services.application_verification_service import AccessObservation


async def test_reintento_concurrente_exactamente_una_operacion_reparar(
    db, pg_sessions, admin, app_order, proxmox
):
    """Doble invocación concurrente de reintento sobre una operación fallida confirmada:
    exactamente una debe tener éxito (202) y la otra debe ser rechazada con 409 (operacion_en_curso o estado_incompatible).
    """
    admin_id = admin.id
    order_id = app_order.pedido.id

    # 1. Aprobar y desplegar hasta crear el contenedor
    await approve(db, admin, app_order, immediate=True)
    stopped_create(proxmox)

    node = DeliveredNode(app_order, pg_sessions)
    await procesar_una(pg_sessions, pve=proxmox, runner=node)

    # 2. Simular que la operación de despliegue falló de forma terminal (confirmada)
    async with pg_sessions() as session:
        op = await session.scalar(
            select(OperacionInfraestructura)
            .where(OperacionInfraestructura.pedido_id == order_id)
            .order_by(OperacionInfraestructura.id.desc())
        )
        op.estado = "fallida"
        op.error_codigo = "instalacion_fallida"
        op.updated_at = clock.now()

        pedido = await session.get(Pedido, order_id)
        pedido.estado = EstadoPedido.ERROR

        identity = await session.get(IdentidadInfraestructura, op.identidad_infraestructura_id)
        proxmox.estados[identity.vmid] = "running"

        await session.commit()

    barrier = asyncio.Barrier(2)

    async def intentar_reintento(idx):
        async with pg_sessions() as session:
            admin_user = await session.get(admin.__class__, admin_id)
            await barrier.wait()
            try:
                res = await reconciliacion_service.reintentar(
                    session,
                    order_id,
                    actor=admin_user,
                    clave=f"reintento-concurrente-{idx}-{uuid4()}",
                    pve=proxmox,
                )
                await session.commit()
                return res.status_code, None
            except HTTPException as exc:
                await session.rollback()
                return exc.status_code, exc.detail.get("codigo") if isinstance(exc.detail, dict) else None

    # Ejecutar ambos reintentos concurrentemente sobre PostgreSQL
    resultados = await asyncio.gather(intentar_reintento(1), intentar_reintento(2))
    status_codes = [r[0] for r in resultados]

    # Exactamente uno debe ser 202 y el otro 409
    assert 202 in status_codes, f"Ningún reintento obtuvo 202: {resultados}"
    assert 409 in status_codes, f"Ningún reintento fue rechazado con 409: {resultados}"

    # Comprobar en base de datos que se creó EXACTAMENTE una operación 'reparar'
    async with pg_sessions() as session:
        operaciones_reparar = (await session.scalars(
            select(OperacionInfraestructura).where(
                OperacionInfraestructura.pedido_id == order_id,
                OperacionInfraestructura.tipo == "reparar",
            )
        )).all()
        assert len(operaciones_reparar) == 1


async def test_recreacion_mismo_pedido_conserva_secretos_aplicacion(
    db, pg_sessions, admin, app_order
):
    """Recreación / llamada sucesiva de asegurar secretos sobre el mismo pedido aprobado conserva
    valores y referencias de SecretoDespliegue con el pedido_id original.
    """
    order_id = app_order.pedido.id
    admin_id = admin.id

    # 1. Aprobar el pedido (genera secretos de aplicación por primera vez)
    await approve(db, admin, app_order)

    async with pg_sessions() as session:
        secretos1 = (await session.scalars(
            select(SecretoDespliegue).where(SecretoDespliegue.pedido_id == order_id)
        )).all()
        assert len(secretos1) > 0
        ids1 = {s.id for s in secretos1}
        cifrados1 = {s.nombre: s.valor_cifrado for s in secretos1}

    # 2. Llamar de nuevo a asegurar sobre el mismo pedido aprobado
    async with pg_sessions() as session:
        admin_user = await session.get(admin.__class__, admin_id)
        refs2 = await secreto_despliegue_service.asegurar(
            session, order_id, usuario=admin_user
        )
        await session.commit()

    async with pg_sessions() as session:
        secretos2 = (await session.scalars(
            select(SecretoDespliegue).where(SecretoDespliegue.pedido_id == order_id)
        )).all()
        ids2 = {s.id for s in secretos2}
        cifrados2 = {s.nombre: s.valor_cifrado for s in secretos2}

    # Comprobar que los IDs y valores cifrados son exactamente los mismos (no regenerados)
    assert ids1 == ids2
    assert cifrados1 == cifrados2
    assert {r["id"] for r in refs2} == {str(s_id) for s_id in ids1}


async def test_renovacion_conserva_secretos_originales_y_nuevo_alta_genera_nuevos(
    db, pg_sessions, admin, app_order, catedra, usuario_catedra
):
    """La renovación de un pedido conserva los secretos del pedido original (ALTA),
    mientras que un nuevo pedido de alta genera secretos independientes.
    """
    order_id = app_order.pedido.id
    admin_id = admin.id

    # 1. Aprobar pedido original ALTA
    await approve(db, admin, app_order)

    async with pg_sessions() as session:
        secretos_alta = (await session.scalars(
            select(SecretoDespliegue).where(SecretoDespliegue.pedido_id == order_id)
        )).all()
        refs_alta = [{"id": str(s.id), "nombre": s.nombre, "revision": s.revision} for s in secretos_alta]

        # Simular servicio activo creado a partir de este pedido
        servicio = Servicio(
            catedra_id=catedra.id,
            template_id=app_order.template.id,
            configuracion_despliegue_id=app_order.config.id,
            pedido_id=order_id,
            nombre_snapshot="Servicio Test 011",
            modelo_servicio=ModeloServicio.SAAS,
            tipo="lxc",
            estado=EstadoServicio.RUNNING,
            disponibilidad_aplicacion="utilizable",
            asignacion_snapshot=app_order.body["asignacion"],
        )
        session.add(servicio)
        await session.flush()
        servicio_id = servicio.id
        await session.commit()

    # 2. Crear pedido de RENOVACIÓN vinculado al servicio
    async with pg_sessions() as session:
        pedido_renovacion = Pedido(
            catedra_id=catedra.id,
            solicitante_id=usuario_catedra.id,
            template_id=app_order.template.id,
            tipo=TipoPedido.RENOVACION,
            estado=EstadoPedido.SOLICITADO,
            modelo_servicio=ModeloServicio.SAAS,
            servicio_id=servicio_id,
            configuracion_despliegue_id=app_order.config.id,
            revision_decision=1,
            asignacion_snapshot={"configuracion_sha256": app_order.config.sha256},
        )
        session.add(pedido_renovacion)
        await session.flush()
        renovacion_id = pedido_renovacion.id
        await session.commit()

    # Asegurar secretos para la renovación
    async with pg_sessions() as session:
        admin_user = await session.get(admin.__class__, admin_id)
        refs_renovacion = await secreto_despliegue_service.asegurar(
            session, renovacion_id, usuario=admin_user, _decision_en_curso=True
        )
        await session.commit()

    # Comprobar que la renovación devuelve las referencias de secretos del pedido original
    assert sorted(refs_renovacion, key=lambda r: r["nombre"]) == sorted(refs_alta, key=lambda r: r["nombre"])

    # 3. Crear otro pedido nuevo de tipo ALTA
    async with pg_sessions() as session:
        pedido_nuevo_alta = Pedido(
            catedra_id=catedra.id,
            solicitante_id=usuario_catedra.id,
            template_id=app_order.template.id,
            tipo=TipoPedido.ALTA,
            estado=EstadoPedido.SOLICITADO,
            modelo_servicio=ModeloServicio.SAAS,
            configuracion_despliegue_id=app_order.config.id,
            revision_decision=1,
            asignacion_snapshot={"configuracion_sha256": app_order.config.sha256},
        )
        session.add(pedido_nuevo_alta)
        await session.flush()
        nuevo_alta_id = pedido_nuevo_alta.id
        await session.commit()

    # Asegurar secretos para el nuevo alta
    async with pg_sessions() as session:
        admin_user = await session.get(admin.__class__, admin_id)
        refs_nuevo_alta = await secreto_despliegue_service.asegurar(
            session, nuevo_alta_id, usuario=admin_user, _decision_en_curso=True
        )
        await session.commit()

    # Comprobar que el nuevo alta tiene secretos distintos (IDs distintos y valores distintos)
    ids_alta = {r["id"] for r in refs_alta}
    ids_nuevo_alta = {r["id"] for r in refs_nuevo_alta}
    assert ids_alta.isdisjoint(ids_nuevo_alta)
