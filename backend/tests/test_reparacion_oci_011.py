"""Hallazgo 5: tras un fallo confirmado, reparar es un intento nuevo y separado sobre el mismo recurso.

Dobles de PVE y del nodo; no sustituyen la validación Proxmox real.
"""
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.intento_despliegue import IntentoDespliegue
from app.models.identidad_infraestructura import IdentidadInfraestructura
from app.models.operacion_infraestructura import OperacionInfraestructura
from app.models.pedido import Pedido, EstadoPedido
from app.models.secreto_despliegue import SecretoDespliegue
from app.models.servicio import Servicio
from app.services.application_verification_service import AccessObservation
from app.services.reconciliacion_service import reintentar
from app.utils.clock import clock
from app.worker import procesar_una, procesar_ingesta_una
from tests.test_admision_aplicaciones_011 import app_order, approve, perfil_capacidad, red_aplicaciones_011, profile_entry  # noqa: F401
from tests.test_creacion_aplicaciones_011 import stopped_create, wake
from tests.test_entrega_aplicaciones_011 import DeliveredNode
from tests.test_ingesta_worker_011 import ConsoleNode


class FailingNode(ConsoleNode):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs); self.start_requests = []
    async def execute(self, request, **kwargs):
        reply = await super().execute(request, **kwargs)
        if request['action'] == 'start': self.start_requests.append(dict(request))
        return reply


class RepairNode(DeliveredNode):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs); self.start_requests = []
    async def execute(self, request, **kwargs):
        reply = await super().execute(request, **kwargs)
        if request['action'] == 'start': self.start_requests.append(dict(request))
        return reply


async def failed_deployment(db, engine, admin, app, proxmox, monkeypatch, *, ct_state):
    pedido_id_global = [app.pedido.id]
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await approve(db, admin, app, immediate=True); stopped_create(proxmox)
    node = FailingNode(app, sessions)
    await procesar_una(sessions, pve=proxmox, runner=node)
    node.state = 'fallido'; node.lose_ack = True
    now = clock.now(); monkeypatch.setattr(clock, 'now', lambda: now)
    clock_box = {'now': now}
    monkeypatch.setattr(clock, 'now', lambda: clock_box['now'])
    for _ in range(2):
        clock_box['now'] += timedelta(seconds=2)
        await wake(db); await procesar_ingesta_una(sessions, runner=node)
    db.expire_all()
    pedido = await db.get(Pedido, pedido_id_global[0])
    assert pedido.estado == EstadoPedido.ERROR
    identity = await db.scalar(select(IdentidadInfraestructura))
    proxmox.estados[identity.vmid] = ct_state
    return sessions, node, clock_box, SimpleNamespace(id=identity.id, vmid=identity.vmid)


async def drive(db, sessions, node, proxmox, clock_box, probe, vmid, *, rounds=14):
    for _ in range(rounds):
        clock_box['now'] += timedelta(seconds=40)
        await wake(db)
        await procesar_una(sessions, pve=proxmox, runner=node, excluir_ingesta=True)  # como el scheduler real
        if node.start_requests: proxmox.estados[vmid] = 'running'  # el job del nodo real arranca el LXC
        await procesar_ingesta_una(sessions, runner=node, pve=proxmox, probe=probe)
        db.expire_all()
        pedido = await db.get(Pedido, (await db.scalar(select(Servicio))).pedido_id)
        if pedido.estado == EstadoPedido.ACTIVO: return True
    return False


@pytest.mark.parametrize('ct_state', ['running', 'stopped'])
async def test_failed_oci_deployment_is_repaired_with_a_new_attempt_on_the_same_resource(
        db, engine, admin, app_order, proxmox, monkeypatch, ct_state):
    app = app_order; pedido_id = app.pedido.id
    sessions, failed_node, clock_box, identity = await failed_deployment(db, engine, admin, app, proxmox, monkeypatch, ct_state=ct_state)
    first = failed_node.start_requests[0]
    secrets_before = [(r.nombre, r.revision) for r in (await db.scalars(select(SecretoDespliegue).order_by(SecretoDespliegue.nombre))).all()]
    created_before = len(proxmox.creados)

    await db.refresh(admin)
    result = await reintentar(db, pedido_id, actor=admin, clave='repair-oci-1'); await db.commit()
    assert result.status_code == 202

    repair = await db.scalar(select(OperacionInfraestructura).where(OperacionInfraestructura.tipo == 'reparar'))
    previous = await db.scalar(select(OperacionInfraestructura).where(OperacionInfraestructura.tipo == 'desplegar'))
    assert repair.operacion_raiz_id == (await db.scalar(select(IntentoDespliegue.operacion_raiz_id).where(
        IntentoDespliegue.operacion_id == previous.id)))
    # El contexto del intento anterior no se hereda: ni la solicitud del job, ni su huella, ni su resultado.
    for key in ('application_job_requested', 'job_fingerprint', 'consola_job_final', 'application_console_ack_pending', 'accion_externa'):
        assert key not in repair.contexto_seguro
    assert repair.identidad_infraestructura_id == identity.id

    repair_node = RepairNode(app, sessions)
    async def probe(instance):
        return AccessObservation(instance['host'], instance['address'], instance['port'], instance['configuration_sha256'], 200)
    done = await drive(db, sessions, repair_node, proxmox, clock_box, probe, identity.vmid)
    op = await db.scalar(select(OperacionInfraestructura).where(OperacionInfraestructura.tipo == 'reparar'))
    assert done, (op.estado, op.fase, op.error_codigo, op.error_detalle_seguro, {a: repair_node.requests.count(a) for a in set(repair_node.requests)}, dict(proxmox.estados),
        [(a.numero, a.estado, a.ultimo_source_seq) for a in (await db.scalars(select(IntentoDespliegue).order_by(IntentoDespliegue.numero))).all()], op.contexto_seguro.get('application_job_requested'), op.contexto_seguro.get('application_job_estado'))

    attempts = list((await db.scalars(select(IntentoDespliegue).order_by(IntentoDespliegue.numero))).all())
    assert [a.numero for a in attempts] == [1, 2] and attempts[0].operacion_raiz_id == attempts[1].operacion_raiz_id
    assert attempts[0].execution_id != attempts[1].execution_id and attempts[0].id != attempts[1].id
    assert [a.estado for a in attempts] == ['fallido', 'confirmado']
    second = repair_node.start_requests[0]
    assert len(repair_node.start_requests) == 1
    for field in ('resource_uuid', 'nonce', 'vmid', 'node', 'pool', 'operacion_raiz_id', 'configuracion_sha256', 'secreto_referencias'):
        assert second[field] == first[field]
    assert second['execution_id'] != first['execution_id'] and second['intento_id'] != first['intento_id']
    assert [(r.nombre, r.revision) for r in (await db.scalars(select(SecretoDespliegue).order_by(SecretoDespliegue.nombre))).all()] == secrets_before
    assert len(proxmox.creados) == created_before
    assert await db.scalar(select(func.count()).select_from(IdentidadInfraestructura)) == 1
    service = await db.scalar(select(Servicio))
    assert service.disponibilidad_aplicacion == 'utilizable'
    assert (await db.get(OperacionInfraestructura, repair.id)).estado == 'confirmada'
    # Encendido: se detiene una sola vez antes del job; ya detenido: no se envía otra parada. Nunca se inicia desde el portal.
    assert len(proxmox.detenidos) == (1 if ct_state == 'running' else 0) and not proxmox.iniciados


async def test_repair_is_refused_while_the_previous_attempt_is_not_confirmed_failed(db, engine, admin, app_order, proxmox, monkeypatch):
    app = app_order; pedido_id = app.pedido.id
    await failed_deployment(db, engine, admin, app, proxmox, monkeypatch, ct_state='running')
    attempt = await db.scalar(select(IntentoDespliegue))
    attempt.estado = 'incierto'; await db.commit(); await db.refresh(admin)
    with pytest.raises(HTTPException) as error:
        await reintentar(db, pedido_id, actor=admin, clave='repair-oci-incierto')
    assert error.value.status_code == 409 and error.value.detail['codigo'] == 'reconciliacion_pendiente'
    assert await db.scalar(select(func.count()).select_from(OperacionInfraestructura).where(OperacionInfraestructura.tipo == 'reparar')) == 0
