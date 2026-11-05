import asyncio
from datetime import timedelta
import threading
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.operacion_infraestructura import OperacionInfraestructura
from app.services import operacion_service
from app.utils.clock import clock
from tests.capacity_helpers import perfil_capacidad
from tests.test_operaciones_recuperacion import queued, prepared_guest, SimulatedCrash


async def test_expired_worker_cannot_dispatch_or_confirm(client, db, pg_sessions, proxmox, perfil_capacidad, prepared_guest, catedra, usuario_catedra, template, auth_admin, monkeypatch):
    from app.services.orquestacion_service import procesar_lease
    now = clock.now()
    monkeypatch.setattr(clock, 'now', lambda: now)
    await queued(client, db, catedra, usuario_catedra, template, auth_admin)
    old = await operacion_service.reclamar(db, owner=uuid4())
    await db.commit()
    now += timedelta(seconds=31)
    async with pg_sessions() as session:
        current = await operacion_service.reclamar(session, owner=uuid4())
        await session.commit()
    await procesar_lease(pg_sessions, old, pve=proxmox)
    assert not proxmox.creados
    await procesar_lease(pg_sessions, current, pve=proxmox)
    operation = await db.get(OperacionInfraestructura, old.id, populate_existing=True)
    assert operation.estado == 'confirmada' and len(proxmox.creados) == 1


async def test_crash_between_post_and_upid_recovers_with_new_database_session(client, db, pg_sessions, proxmox, perfil_capacidad, prepared_guest, catedra, usuario_catedra, template, auth_admin, monkeypatch):
    from app.worker import procesar_una
    now = clock.now()
    monkeypatch.setattr(clock, 'now', lambda: now)
    await queued(client, db, catedra, usuario_catedra, template, auth_admin)
    async def cut(*args):
        raise SimulatedCrash()
    with pytest.raises(SimulatedCrash):
        await procesar_una(pg_sessions, pve=proxmox, after_dispatch=cut)
    now += timedelta(seconds=31)
    await procesar_una(pg_sessions, pve=proxmox)
    operation = await db.scalar(select(OperacionInfraestructura).execution_options(populate_existing=True))
    assert operation.estado == 'confirmada' and operation.lease_generation == 2
    assert len(proxmox.creados) == 1


async def test_claims_serialize_even_when_external_nextid_repeats(db, pg_sessions, proxmox, perfil_capacidad, monkeypatch):
    from app.services.identidad_infra_service import reclamar
    operations = [OperacionInfraestructura(tipo='desplegar', actor_tipo='sistema', actor_id_normalizado='test',
        idempotency_key=f'claim-{index}', request_hash='a' * 64, estado='pendiente',
        contexto_seguro={'catedra_id': 1, 'asignacion': {'definition_sha256': 'b'*64, 'bundle_sha256': 'c'*64},
            'destino': {'nodo': 'pve1', 'storage': 'local-lvm'}}) for index in range(4)]
    db.add_all(operations)
    await db.commit()
    ids = [operation.id for operation in operations]
    monkeypatch.setattr(proxmox, 'get_next_vmid', lambda: 100)
    barrier = asyncio.Barrier(4)
    async def claim(operation_id):
        async with pg_sessions() as session, session.begin():
            operation = await session.get(OperacionInfraestructura, operation_id)
            await barrier.wait()
            identity = await reclamar(session, operation, pve=proxmox)
            return identity.vmid
    values = await asyncio.gather(*(claim(operation_id) for operation_id in ids), return_exceptions=True)
    assert not any(isinstance(value, BaseException) for value in values), values
    assert sorted(values) == [100, 101, 102, 103]


async def test_independent_http_query_remains_responsive_during_slow_post(client, db, pg_sessions, proxmox, perfil_capacidad, prepared_guest, catedra, usuario_catedra, template, auth_admin, monkeypatch):
    from app.worker import procesar_una
    await queued(client, db, catedra, usuario_catedra, template, auth_admin)
    started, release = threading.Event(), threading.Event()
    create = proxmox.create_lxc
    def slow(*args, **kwargs):
        started.set()
        if not release.wait(timeout=3):
            raise TimeoutError()
        return create(*args, **kwargs)
    monkeypatch.setattr(proxmox, 'create_lxc', slow)
    task = asyncio.create_task(procesar_una(pg_sessions, pve=proxmox))
    try:
        for _ in range(100):
            if started.is_set():
                break
            await asyncio.sleep(0.01)
        assert started.is_set()
        response = await asyncio.wait_for(client.get('/servicios/', headers=auth_admin), timeout=0.7)
        assert response.status_code == 200 and not task.done()
    finally:
        release.set()
        await task
