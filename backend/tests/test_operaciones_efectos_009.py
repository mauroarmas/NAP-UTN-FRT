from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.operacion_infraestructura import OperacionInfraestructura
from app.models.servicio import EstadoServicio, Servicio
from app.utils.clock import clock
from tests.capacity_helpers import perfil_capacidad, materializado
from tests.test_operaciones_recuperacion import queued, prepared_guest
from app.worker import procesar_una


async def test_stop_retains_compute_until_task_and_stopped_are_confirmed(client, db, engine, proxmox, perfil_capacidad, catedra, usuario_catedra, template, auth_admin, monkeypatch):
    now = clock.now()
    monkeypatch.setattr(clock, 'now', lambda: now)
    service, ledger = await materializado(db, proxmox, catedra, usuario_catedra, template)
    proxmox.start_lxc('pve1', 100)
    service.estado = EstadoServicio.RUNNING
    ledger.vcpus_retenidos, ledger.ram_mb_retenida = 2, 1024
    await db.commit()
    proxmox.configure_task('pve1', 'UPID:pve1:task:stop', [{'status': 'running'}, {'status': 'stopped', 'exitstatus': 'OK'}])
    response = await client.post(f'/servicios/{service.id}/stop', headers=auth_admin | {'Idempotency-Key': 'stop-confirmed'}, json={})
    assert response.status_code == 202 and not proxmox.detenidos
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await procesar_una(sessions, pve=proxmox)
    await db.refresh(ledger)
    assert ledger.vcpus_retenidos == 2 and ledger.disk_bytes_retenidos > 0
    now += timedelta(seconds=3)
    await procesar_una(sessions, pve=proxmox)
    await db.refresh(ledger)
    await db.refresh(service)
    assert ledger.vcpus_retenidos == ledger.ram_mb_retenida == 0
    assert ledger.disk_bytes_retenidos > 0 and service.estado == EstadoServicio.STOPPED


async def test_delete_waits_for_stop_then_confirms_absence_before_local_retirement(client, db, engine, proxmox, perfil_capacidad, catedra, usuario_catedra, template, auth_admin, monkeypatch):
    now = clock.now()
    monkeypatch.setattr(clock, 'now', lambda: now)
    service, ledger = await materializado(db, proxmox, catedra, usuario_catedra, template)
    proxmox.start_lxc('pve1', 100)
    service.estado = EstadoServicio.RUNNING
    ledger.vcpus_retenidos, ledger.ram_mb_retenida = 2, 1024
    await db.commit()
    proxmox.configure_task('pve1', 'UPID:pve1:task:stop', [{'status': 'running'}, {'status': 'stopped', 'exitstatus': 'OK'}])
    response = await client.delete(f'/servicios/{service.id}', headers=auth_admin | {'Idempotency-Key': 'delete-confirmed'})
    assert response.status_code == 202
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await procesar_una(sessions, pve=proxmox)
    await db.refresh(service)
    assert service.deleted_at is None and not proxmox.eliminados
    now += timedelta(seconds=3)
    await procesar_una(sessions, pve=proxmox)
    await db.refresh(ledger)
    await db.refresh(service)
    assert service.deleted_at is not None and ledger.liberado_at is not None
    assert ledger.disk_bytes_retenidos == ledger.vcpus_retenidos == ledger.ram_mb_retenida == 0
    operation = await db.get(OperacionInfraestructura, UUID(response.json()['operation_id']), populate_existing=True)
    assert operation.estado == 'confirmada' and len(proxmox.eliminados) == 1


async def test_response_timeout_reconciles_without_second_create(client, db, engine, proxmox, perfil_capacidad, prepared_guest, catedra, usuario_catedra, template, auth_admin, monkeypatch):
    now = clock.now()
    monkeypatch.setattr(clock, 'now', lambda: now)
    await queued(client, db, catedra, usuario_catedra, template, auth_admin)
    actual_create = proxmox.create_lxc
    def response_lost(*args, **kwargs):
        actual_create(*args, **kwargs)
        raise TimeoutError('Sensitive upstream response must not be exposed')
    monkeypatch.setattr(proxmox, 'create_lxc', response_lost)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await procesar_una(sessions, pve=proxmox)
    operation = await db.scalar(select(OperacionInfraestructura).execution_options(populate_existing=True))
    assert operation.estado == 'incierta' and operation.upid is None
    now += timedelta(seconds=3)
    await procesar_una(sessions, pve=proxmox)
    await db.refresh(operation)
    assert operation.estado == 'confirmada' and len(proxmox.creados) == 1


async def test_resource_without_task_evidence_stays_uncertain(client, db, engine, proxmox, perfil_capacidad, prepared_guest, catedra, usuario_catedra, template, auth_admin, monkeypatch):
    now = clock.now()
    monkeypatch.setattr(clock, 'now', lambda: now)
    await queued(client, db, catedra, usuario_catedra, template, auth_admin)
    actual_create = proxmox.create_lxc
    def response_and_history_lost(*args, **kwargs):
        actual_create(*args, **kwargs)
        proxmox.task_history.clear()
        raise TimeoutError()
    monkeypatch.setattr(proxmox, 'create_lxc', response_and_history_lost)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await procesar_una(sessions, pve=proxmox)
    now += timedelta(seconds=3)
    await procesar_una(sessions, pve=proxmox)
    operation = await db.scalar(select(OperacionInfraestructura).execution_options(populate_existing=True))
    assert operation.estado == 'incierta' and len(proxmox.creados) == 1
    assert await db.scalar(select(Servicio)) is None


async def test_unprepared_definition_never_sends_create(client, db, engine, proxmox, perfil_capacidad, catedra, usuario_catedra, template, auth_admin):
    await queued(client, db, catedra, usuario_catedra, template, auth_admin)
    await procesar_una(async_sessionmaker(engine, expire_on_commit=False), pve=proxmox)
    operation = await db.scalar(select(OperacionInfraestructura))
    assert operation.estado == 'fallida' and operation.dispatch_started_at is None and not proxmox.creados


async def test_retry_repairs_same_identity_without_recreating(client, db, engine, proxmox, perfil_capacidad, prepared_guest, catedra, usuario_catedra, template, auth_admin):
    request, operation_id = await queued(client, db, catedra, usuario_catedra, template, auth_admin)
    proxmox.configure_task('pve1', 'UPID:pve1:task:create', [{'status': 'stopped', 'exitstatus': 'ERROR: simulated partial failure'}])
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await procesar_una(sessions, pve=proxmox)
    previous = await db.get(OperacionInfraestructura, UUID(operation_id), populate_existing=True)
    assert previous.estado == 'fallida'
    response = await client.post(f'/pedidos/{request.id}/reintentar', headers=auth_admin | {'Idempotency-Key': 'repair-same'}, json={})
    assert response.status_code == 202, response.text
    await procesar_una(sessions, pve=proxmox)
    current = await db.get(OperacionInfraestructura, UUID(response.json()['operation_id']), populate_existing=True)
    assert current.estado == 'confirmada' and current.tipo == 'reparar'
    assert previous.identidad_infraestructura_id == current.identidad_infraestructura_id and len(proxmox.creados) == 1
