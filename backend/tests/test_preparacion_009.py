"""Preparación durable con runner explícitamente simulado y PVE doble."""
from copy import deepcopy
from datetime import timedelta
import json
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import get_settings
from app.models.definicion_servicio import DefinicionServicio
from app.models.operacion_infraestructura import OperacionInfraestructura
from app.models.pedido import Pedido
from app.models.servicio import Servicio
from app.utils.clock import clock
from app.utils.secretos import configured_keyring
from tests.capacity_helpers import perfil_capacidad
from tests.test_operaciones_recuperacion import queued


@pytest.fixture
def installed_definition(monkeypatch):
    from app.services import catalogo_service
    async def available(value, **kwargs):
        # Solo disponibilidad física se sustituye. Definición/evidencia y
        # snapshot se comprueban con el servicio real.
        assert value['product'] == 'linux'
    monkeypatch.setattr(catalogo_service, 'comprobar_disponibilidad', available)
    monkeypatch.setattr(get_settings(), 'service_artifacts', {'linux-capacity-test:1.0.0': {
        'nodes': ['pve1'], 'network_profile_id': 'test-network'}})
    monkeypatch.setattr(get_settings(), 'network_profiles', {'test-network': {
        'bridge': 'vmbr0', 'nodes': ['pve1'], 'allowed_cidrs': ['10.50.0.0/24'],
        'client_cidrs': ['10.50.0.0/24']}})


class PreparedRunner:
    def __init__(self, sessions, *, uncertain_first=False, address='10.50.0.101'):
        self.sessions, self.requests = sessions, []
        self.uncertain_first, self.address = uncertain_first, address
    async def execute(self, value):
        async with self.sessions() as db:
            service = await db.scalar(select(Servicio).where(Servicio.proxmox_vmid == str(value['vmid'])))
            assert service and service.credenciales_encrypted
            assert configured_keyring().decrypt(service.credenciales_encrypted,
                context=f'servicio:{service.id}:secretos') == value['secrets']
            operation = await db.get(OperacionInfraestructura, UUID(value['operation_id']))
            assert operation.contexto_seguro['bootstrap_started'] is True
        self.requests.append(deepcopy(value))
        result = {key: value[key] for key in ['protocol', 'operation_id', 'action', 'resource_uuid']}
        result.update(status='succeeded', phase='verified', observed_at=clock.now().isoformat(), identity_verified=True)
        if self.uncertain_first and len(self.requests) == 1:
            result.update(status='unconfirmed', error={'code': 'UNCONFIRMED', 'phase': 'verified', 'retryable': True,
                'message': 'Resultado no confirmado; revisar la operación'})
        else:
            result['result'] = {'ready': True, 'bootstrap_completed': True, 'username': 'napadmin',
                'addresses': [self.address], 'checks': ['linux-ready-v1']}
        return result


async def test_preparation_encrypts_before_effect_and_does_not_deliver_access(client, db, engine, proxmox,
        perfil_capacidad, installed_definition, catedra, usuario_catedra, template, auth_admin, caplog):
    from app.worker import procesar_una
    pedido, operation_id = await queued(client, db, catedra, usuario_catedra, template, auth_admin)
    pedido_id = pedido.id
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    runner = PreparedRunner(sessions)
    await procesar_una(sessions, pve=proxmox, runner=runner)
    db.expire_all()
    operation = await db.get(OperacionInfraestructura, UUID(operation_id))
    assert operation.estado == 'confirmada', (operation.error_codigo, operation.error_detalle_seguro)
    service = await db.get(Servicio, operation.servicio_id)
    assert service.acceso_metadata['local_health'] is True
    assert service.disponibilidad_aplicacion == 'no_verificada'
    assert (await db.get(Pedido, pedido_id)).estado.value == 'en_despliegue'
    value = runner.requests[0]
    assert value['secrets']['guest_password'] not in caplog.text + json.dumps(service.acceso_metadata) + json.dumps(operation.contexto_seguro)
    marker = json.loads(proxmox.creados[0]['description'])['nap']
    assert marker['cluster_uuid'] == value['cluster_uuid'] and marker['definition_sha256'] == value['definition_sha256']
    assert marker['bundle_sha256'] == value['bundle_sha256']


async def test_retry_uses_same_ciphertext_and_secrets_without_a_second_create(client, db, engine, proxmox,
        perfil_capacidad, installed_definition, catedra, usuario_catedra, template, auth_admin, monkeypatch):
    from app.worker import procesar_una
    now = clock.now(); monkeypatch.setattr(clock, 'now', lambda: now)
    _, operation_id = await queued(client, db, catedra, usuario_catedra, template, auth_admin)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    runner = PreparedRunner(sessions, uncertain_first=True)
    await procesar_una(sessions, pve=proxmox, runner=runner)
    db.expire_all()
    service = await db.scalar(select(Servicio)); ciphertext = service.credenciales_encrypted
    assert (await db.get(OperacionInfraestructura, UUID(operation_id))).estado == 'incierta'
    now += timedelta(seconds=31)
    await procesar_una(sessions, pve=proxmox, runner=runner)
    db.expire_all()
    assert (await db.get(OperacionInfraestructura, UUID(operation_id))).estado == 'confirmada'
    assert len(proxmox.creados) == 1 and len(runner.requests) == 2
    assert runner.requests[0] == runner.requests[1]
    assert (await db.scalar(select(Servicio))).credenciales_encrypted == ciphertext


async def test_retired_approved_definition_keeps_its_original_preparation(client, db, engine, proxmox,
        perfil_capacidad, installed_definition, catedra, usuario_catedra, template, auth_admin):
    from app.worker import procesar_una
    _, operation_id = await queued(client, db, catedra, usuario_catedra, template, auth_admin)
    definition = await db.get(DefinicionServicio, template.definicion_version_id)
    definition.estado = 'retirada'; await db.commit()
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    runner = PreparedRunner(sessions)
    await procesar_una(sessions, pve=proxmox, runner=runner)
    db.expire_all()
    assert (await db.get(OperacionInfraestructura, UUID(operation_id))).estado == 'confirmada'
    assert len(runner.requests) == 1


async def test_unexpected_guest_network_stays_unconfirmed_without_access(client, db, engine, proxmox,
        perfil_capacidad, installed_definition, catedra, usuario_catedra, template, auth_admin):
    from app.worker import procesar_una
    _, operation_id = await queued(client, db, catedra, usuario_catedra, template, auth_admin)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await procesar_una(sessions, pve=proxmox, runner=PreparedRunner(sessions, address='192.0.2.100'))
    db.expire_all()
    assert (await db.get(OperacionInfraestructura, UUID(operation_id))).estado == 'incierta'
    service = await db.scalar(select(Servicio))
    assert service.disponibilidad_aplicacion == 'no_verificada' and not service.acceso_metadata.get('local_health')


async def test_old_worker_cannot_confirm_preparation_after_lease_takeover(client, db, engine, proxmox,
        perfil_capacidad, installed_definition, catedra, usuario_catedra, template, auth_admin):
    import asyncio
    from uuid import uuid4
    from app.worker import procesar_una
    _, operation_id = await queued(client, db, catedra, usuario_catedra, template, auth_admin)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    started, release = asyncio.Event(), asyncio.Event()
    class HeldRunner(PreparedRunner):
        async def execute(self, value):
            result = await super().execute(value)
            started.set()
            await release.wait()
            return result
    task = asyncio.create_task(procesar_una(sessions, pve=proxmox, runner=HeldRunner(sessions)))
    try:
        await asyncio.wait_for(started.wait(), timeout=3)
        db.expire_all()
        operation = await db.get(OperacionInfraestructura, UUID(operation_id))
        operation.lease_generation += 1
        operation.lease_owner = uuid4()
        operation.lease_until = clock.now() + timedelta(seconds=30)
        await db.commit()
    finally:
        release.set()
        await asyncio.wait_for(task, timeout=3)
    db.expire_all()
    operation = await db.get(OperacionInfraestructura, UUID(operation_id))
    service = await db.scalar(select(Servicio))
    assert operation.estado == 'en_curso' and not service.acceso_metadata['local_health']
