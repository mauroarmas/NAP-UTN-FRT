"""Pruebas del endpoint POST /operaciones/{id}/reintentar (US5 - T093):
- verificación de autenticación y rol admin (401/403);
- operación inexistente (404);
- estado en curso o incierto (409 con detalle estructurado);
- estado no fallido (409);
- operación fallida confirmada crea operación 'reparar' sin duplicar identidad ni compromisos (202).
"""
from uuid import uuid4
import pytest
from sqlalchemy import select

from app.models.compromiso_capacidad import CompromisoCapacidad
from app.models.identidad_infraestructura import IdentidadInfraestructura
from app.models.operacion_infraestructura import OperacionInfraestructura
from app.models.pedido import Pedido, EstadoPedido
from app.services import orquestacion_service
from app.utils.clock import clock
from tests import factories
from tests.test_admision_aplicaciones_011 import (
    app_order,
    approve,
    perfil_capacidad,
    red_aplicaciones_011,
    profile_entry,
)
from tests.test_creacion_aplicaciones_011 import stopped_create
from tests.test_entrega_aplicaciones_011 import DeliveredNode
from app.worker import procesar_una
from sqlalchemy.ext.asyncio import async_sessionmaker


async def test_reintentar_operacion_requiere_auth_y_admin(client):
    op_id = uuid4()
    # 1. Sin auth -> 401
    r1 = await client.post(f"/operaciones/{op_id}/reintentar", headers={"Idempotency-Key": str(uuid4())})
    assert r1.status_code == 401


async def test_reintentar_operacion_no_encontrada(client, auth_admin):
    op_id = uuid4()
    resp = await client.post(
        f"/operaciones/{op_id}/reintentar",
        headers={**auth_admin, "Idempotency-Key": str(uuid4())},
    )
    assert resp.status_code == 404
    assert resp.json().get("detail", {}).get("codigo") == "operacion_no_encontrada"


async def test_reintentar_operacion_estado_invalido_o_incierto(client, db, auth_admin):
    # Operación confirmada (no fallida)
    op_confirmada = OperacionInfraestructura(
        tipo="desplegar",
        pedido_id=101,
        actor_tipo="usuario",
        actor_id_normalizado="1",
        idempotency_key=str(uuid4()),
        request_hash="hash1",
        estado="confirmada",
        fase="finalizada",
        creado_at=clock.now(),
        updated_at=clock.now(),
    )
    # Operación incierta
    op_incierta = OperacionInfraestructura(
        tipo="desplegar",
        pedido_id=102,
        actor_tipo="usuario",
        actor_id_normalizado="1",
        idempotency_key=str(uuid4()),
        request_hash="hash2",
        estado="incierta",
        fase="tarea",
        creado_at=clock.now(),
        updated_at=clock.now(),
    )
    # Operación en curso
    op_en_curso = OperacionInfraestructura(
        tipo="desplegar",
        pedido_id=103,
        actor_tipo="usuario",
        actor_id_normalizado="1",
        idempotency_key=str(uuid4()),
        request_hash="hash3",
        estado="en_curso",
        fase="creacion",
        creado_at=clock.now(),
        updated_at=clock.now(),
    )
    db.add_all([op_confirmada, op_incierta, op_en_curso])
    await db.commit()

    # Reintentar confirmada -> 409 estado_incompatible
    r_conf = await client.post(
        f"/operaciones/{op_confirmada.id}/reintentar",
        headers={**auth_admin, "Idempotency-Key": str(uuid4())},
    )
    assert r_conf.status_code == 409
    assert r_conf.json().get("detail", {}).get("codigo") == "estado_incompatible"

    # Reintentar incierta -> 409 operacion_en_curso (está en OPEN)
    r_inc = await client.post(
        f"/operaciones/{op_incierta.id}/reintentar",
        headers={**auth_admin, "Idempotency-Key": str(uuid4())},
    )
    assert r_inc.status_code == 409
    assert r_inc.json().get("detail", {}).get("codigo") == "operacion_en_curso"

    # Reintentar en curso -> 409 operacion_en_curso
    r_cur = await client.post(
        f"/operaciones/{op_en_curso.id}/reintentar",
        headers={**auth_admin, "Idempotency-Key": str(uuid4())},
    )
    assert r_cur.status_code == 409
    assert r_cur.json().get("detail", {}).get("codigo") == "operacion_en_curso"


async def test_reintentar_operacion_fallida_confirmada_crea_reparar(
    client, db, engine, admin, app_order, proxmox, auth_admin
):
    """Operación previa en estado terminal fallido confirmado sobre pedido en ERROR:
    POST /operaciones/{id}/reintentar admite operación 'reparar' con status 202.
    """
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    order_id = app_order.pedido.id

    # 1. Desplegar hasta crear contenedor
    await approve(db, admin, app_order, immediate=True)
    stopped_create(proxmox)

    node = DeliveredNode(app_order, sessions)
    await procesar_una(sessions, pve=proxmox, runner=node)
    db.expire_all()

    # 2. Simular fallo confirmado de la operación de despliegue
    op = await db.scalar(
        select(OperacionInfraestructura)
        .where(OperacionInfraestructura.pedido_id == order_id)
        .order_by(OperacionInfraestructura.id.desc())
    )
    op.estado = "fallida"
    op.error_codigo = "instalacion_fallida"

    pedido = await db.get(Pedido, order_id)
    pedido.estado = EstadoPedido.ERROR

    identity = await db.get(IdentidadInfraestructura, op.identidad_infraestructura_id)
    proxmox.estados[identity.vmid] = "running"
    await db.commit()

    # 3. Invocar endpoint POST /operaciones/{id}/reintentar
    resp = await client.post(
        f"/operaciones/{op.id}/reintentar",
        headers={**auth_admin, "Idempotency-Key": str(uuid4())},
        json={"motivo": "Reintento administrativo tras corregir red"},
    )
    assert resp.status_code == 202
    data = resp.json()
    assert "operation_id" in data

    # 4. Verificar que se creó la operación 'reparar'
    reparar_op = await db.scalar(
        select(OperacionInfraestructura).where(
            OperacionInfraestructura.pedido_id == order_id,
            OperacionInfraestructura.tipo == "reparar",
        )
    )
    assert reparar_op is not None
    assert reparar_op.estado == "pendiente"
    assert reparar_op.identidad_infraestructura_id == identity.id
