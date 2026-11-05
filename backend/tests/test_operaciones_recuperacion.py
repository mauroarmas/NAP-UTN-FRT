from datetime import timedelta

import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.operacion_infraestructura import OperacionInfraestructura
from app.models.compromiso_capacidad import CompromisoCapacidad
from app.models.identidad_infraestructura import IdentidadInfraestructura
from app.models.servicio import Servicio
from app.models.pedido import Pedido
from app.utils.clock import clock
from tests.capacity_helpers import perfil_capacidad
from tests.test_liberacion_009 import approved


class SimulatedCrash(BaseException):
    pass


@pytest.fixture
def prepared_guest(monkeypatch):
    from app.services import bootstrap_service
    async def local_preparation(*args, **kwargs):
        # Puerto de preparación local simulado. No acredita un runner ni red reales.
        return {'identity_verified': True, 'local_health': True,
                'acceso_metadata': {'metodo': 'consola', 'validacion': 'simulada'}}
    async def validated_definition(*args, **kwargs):
        return {'net0': 'name=eth0,bridge=vmbr0,ip=dhcp'}
    monkeypatch.setattr(bootstrap_service, 'preparar', local_preparation)
    monkeypatch.setattr(bootstrap_service, 'validar_preparacion', validated_definition)


async def queued(client, db, catedra, usuario, template, headers):
    pedido = await approved(client, db, catedra, usuario, template, headers)
    response = await client.post(f'/servicios/desplegar/{pedido.id}', headers=headers | {'Idempotency-Key': 'queued-deployment'}, json={})
    assert response.status_code == 202, response.text
    return pedido, response.json()['operation_id']


async def test_crash_after_post_before_upid_commit_reconciles_one_resource(client, db, engine, proxmox, perfil_capacidad, prepared_guest, catedra, usuario_catedra, template, auth_admin, monkeypatch):
    from app.worker import procesar_una
    now = clock.now()
    monkeypatch.setattr(clock, 'now', lambda: now)
    pedido, operation_id = await queued(client, db, catedra, usuario_catedra, template, auth_admin)
    request_id = pedido.id
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async def crash(*args):
        raise SimulatedCrash()
    with pytest.raises(SimulatedCrash):
        await procesar_una(sessions, pve=proxmox, after_dispatch=crash)
    assert len(proxmox.creados) == 1
    identity = await db.scalar(select(IdentidadInfraestructura))
    resource_uuid = identity.resource_uuid
    now += timedelta(seconds=31)
    await procesar_una(sessions, pve=proxmox)
    await db.refresh(identity)
    assert identity.resource_uuid == resource_uuid
    assert len(proxmox.creados) == 1
    assert await db.scalar(select(func.count()).select_from(Servicio)) == 1
    operation = await db.get(OperacionInfraestructura, __import__('uuid').UUID(operation_id), populate_existing=True)
    assert operation.estado == 'confirmada'
    service = await db.scalar(select(Servicio))
    assert service.disponibilidad_aplicacion == 'no_verificada'
    request = await db.get(Pedido, request_id, populate_existing=True)
    assert request.estado.value == 'en_despliegue'


async def test_late_task_does_not_confirm_until_terminal_and_never_recreates(client, db, engine, proxmox, perfil_capacidad, prepared_guest, catedra, usuario_catedra, template, auth_admin, monkeypatch):
    from app.worker import procesar_una
    now = clock.now()
    monkeypatch.setattr(clock, 'now', lambda: now)
    await queued(client, db, catedra, usuario_catedra, template, auth_admin)
    proxmox.configure_task('pve1', 'UPID:pve1:task:create', [{'status': 'running'}, {'status': 'stopped', 'exitstatus': 'OK'}])
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await procesar_una(sessions, pve=proxmox)
    operation = await db.scalar(select(OperacionInfraestructura).execution_options(populate_existing=True))
    assert operation.estado in {'en_curso', 'incierta'}
    assert operation.upid and len(proxmox.creados) == 1
    now += timedelta(seconds=3)
    await procesar_una(sessions, pve=proxmox)
    await db.refresh(operation)
    assert operation.estado == 'confirmada' and len(proxmox.creados) == 1


async def test_failed_task_with_existing_resource_retains_commitment(client, db, engine, proxmox, perfil_capacidad, prepared_guest, catedra, usuario_catedra, template, auth_admin):
    from app.worker import procesar_una
    await queued(client, db, catedra, usuario_catedra, template, auth_admin)
    proxmox.configure_task('pve1', 'UPID:pve1:task:create', [{'status': 'stopped', 'exitstatus': 'ERROR: TEST-FAILURE'}])
    await procesar_una(async_sessionmaker(engine, expire_on_commit=False), pve=proxmox)
    ledger = await db.scalar(select(CompromisoCapacidad).execution_options(populate_existing=True))
    assert ledger.liberado_at is None and ledger.vcpus_retenidos > 0 and ledger.disk_bytes_retenidos > 0
    operation = await db.scalar(select(OperacionInfraestructura))
    assert operation.estado in {'fallida', 'incierta'}
    assert len(proxmox.creados) == 1


async def test_foreign_resource_with_same_hostname_is_never_adopted_or_deleted(client, db, engine, proxmox, perfil_capacidad, prepared_guest, catedra, usuario_catedra, template, auth_admin):
    from app.worker import procesar_una
    pedido, _ = await queued(client, db, catedra, usuario_catedra, template, auth_admin)
    proxmox.recursos.append({'type': 'lxc', 'vmid': 100, 'node': 'pve1', 'status': 'running', 'name': f'ct-cat{catedra.id}-ped{pedido.id}'})
    proxmox.configuraciones[('pve1', 100)] = {'cores': 1, 'memory': 128, 'description': 'Recurso externo sin marca NAP'}
    await procesar_una(async_sessionmaker(engine, expire_on_commit=False), pve=proxmox)
    service = await db.scalar(select(Servicio))
    assert service is None or service.proxmox_vmid != '100'
    assert ('pve1', 100) not in proxmox.eliminados
    assert proxmox.configuraciones[('pve1', 100)]['description'] == 'Recurso externo sin marca NAP'


async def test_late_creation_outside_coverage_is_stopped_without_delivery(client, db, engine, proxmox, perfil_capacidad, prepared_guest, catedra, usuario_catedra, template, auth_admin, monkeypatch):
    from app.worker import procesar_una
    now = clock.now()
    monkeypatch.setattr(clock, 'now', lambda: now)
    await queued(client, db, catedra, usuario_catedra, template, auth_admin)
    proxmox.configure_task('pve1', 'UPID:pve1:task:create', [{'status': 'running'}, {'status': 'stopped', 'exitstatus': 'OK'}])
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await procesar_una(sessions, pve=proxmox)
    now += timedelta(days=32)
    await procesar_una(sessions, pve=proxmox)
    ledger = await db.scalar(select(CompromisoCapacidad).execution_options(populate_existing=True))
    service = await db.scalar(select(Servicio))
    assert ledger.vcpus_retenidos == ledger.ram_mb_retenida == 0 and ledger.disk_bytes_retenidos > 0
    assert service.estado.value in {'paused', 'stopped'} and service.disponibilidad_aplicacion != 'utilizable'
    assert proxmox.detenidos and len(proxmox.creados) == 1
