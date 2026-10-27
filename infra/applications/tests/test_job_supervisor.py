"""Durability tests use local private files and a detached service double, not PVE."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from infra.applications.job.protocol import JobError, canonical, parse_response, public_identity
from infra.applications.job.state import StateStore
from infra.applications.job.supervisor import Supervisor, SystemdService
from infra.applications.profiles.registry import ProfileRegistry
from infra.applications.tests.test_application_profiles import certify, reference


class DetachedService:
    def __init__(self):
        self.units, self.starts = {}, []
        self.lose_response = False

    def start(self, execution_id, *, timeout_seconds):
        self.starts.append(execution_id)
        self.units[execution_id] = {'state': 'active', 'invocation_id': str(uuid4()), 'result': 'success'}
        if self.lose_response: raise TimeoutError('fixture: SSH response lost')

    def observe(self, execution_id):
        return self.units.get(execution_id, {'state': 'absent', 'invocation_id': None, 'result': None})


class Credentials:
    def __init__(self): self.values = {}; self.fail = False
    def stage(self, execution_id, *, fingerprint, secretos):
        if self.fail: raise JobError('NO_SPACE')
        self.values[execution_id] = deepcopy(secretos)
    def discard(self, execution_id, **kwargs): self.values.pop(execution_id, None)


@pytest.fixture
def rig(tmp_path, profile_entry):
    entry = certify(profile_entry)
    definition = entry['definition']
    config = {'schema_version': 'nap-deployment/1', 'origen': 'imagen_docker', 'modelo_servicio': 'saas',
        'perfil': reference(entry), 'base': definition['base'], 'minimum_resources': definition['minimum_resources'],
        'access': {'tipo': 'web', 'puerto': 8080, 'politica': 'web-managed', 'upstream': 'http',
            'probe': {'tipo': 'http', 'path': '/health', 'estados': [200], 'timeout_segundos': 5}, 'websocket': False},
        'variables': {'COURSE': 'Testing'}, 'secretos': [{'nombre': 'APP_PASSWORD', 'etiqueta': 'Acceso', 'modo': 'generado'}],
        'persistencia': ['/data'], 'imagen': {'repositorio': 'registry.example.edu/campus/demo',
            'manifest_digest': 'sha256:'+'c'*64, 'config_digest': 'sha256:'+'d'*64,
            'os': 'linux', 'arquitectura': 'amd64', 'registry_profile_id': 'campus'}}
    request = {'protocol': 'nap-application-job/1', 'action': 'start',
        **{key: str(uuid4()) for key in ('operation_id', 'operacion_raiz_id', 'intento_id', 'execution_id', 'resource_uuid')},
        'cluster_uuid': definition['cluster_uuid'], 'node': 'proxmox', 'vmid': 900011, 'pool': 'nap-apps',
        'lease_generation': 1, 'nonce': 'e'*64, 'perfil': reference(entry),
        'configuracion_sha256': sha256(canonical(config)).hexdigest(), 'configuracion': config,
        'secretos': {'APP_PASSWORD': 'fixture-private-password-011'},
        'secreto_referencias': [{'id': str(uuid4()), 'nombre': 'APP_PASSWORD', 'revision': 1}]}
    store = StateStore(tmp_path / 'state')
    service, credentials = DetachedService(), Credentials()
    context = SimpleNamespace(boot=str(uuid4()), foreign=False)
    stores = [store]
    def owner(identity):
        if context.foreign: raise JobError('IDENTITY_MISMATCH')
        assert 'nonce' not in identity
        return True
    def make_supervisor():
        selected = store if len(stores) == 1 else StateStore(tmp_path / 'state')
        stores.append(selected)
        return Supervisor(store=selected, profiles=ProfileRegistry({'docker-ubuntu24:1': entry}),
            service=service, credentials=credentials, assert_owner=owner,
            cluster_uuid=definition['cluster_uuid'], node='proxmox', platform=definition['platform'],
            boot_id=lambda: context.boot)
    yield SimpleNamespace(request=request, store=store, path=tmp_path/'state', service=service,
        credentials=credentials, context=context, supervisor=make_supervisor(), make_supervisor=make_supervisor)
    for item in stores: item.close()


def call(rig, action='start', **changes):
    request = deepcopy(rig.request)
    if action != 'start':
        for key in ('configuracion', 'secretos', 'secreto_referencias'): request.pop(key)
    request.update(action=action, **changes)
    response = rig.supervisor.handle(canonical(request))
    assert parse_response(canonical(response), request=request) == response
    return response['data']


def test_reconnect_replays_same_detached_job_and_never_persists_credentials(rig):
    first = call(rig)
    assert first['estado'] == 'ejecutando'
    rig.supervisor = rig.make_supervisor()  # New SSH/controller object, same durable node.
    assert call(rig)['fingerprint'] == first['fingerprint']
    assert call(rig, 'status')['execution_id'] == first['execution_id']
    assert rig.service.starts == [rig.request['execution_id']]
    for file in rig.path.iterdir():
        if file.is_file():
            raw = file.read_bytes()
            assert rig.request['nonce'].encode() not in raw
            assert b'fixture-private-password-011' not in raw


def test_lost_start_response_is_reconciled_without_another_start(rig):
    rig.service.lose_response = True
    assert call(rig)['estado'] == 'incierto'
    assert call(rig, 'status')['estado'] == 'ejecutando'
    call(rig)
    assert len(rig.service.starts) == 1


def test_fencing_and_conflicting_content_do_not_restart_or_kill_job(rig):
    call(rig); call(rig, 'status', lease_generation=2)
    with pytest.raises(JobError, match='STALE_CONTROLLER'): call(rig)
    with pytest.raises(JobError, match='EXECUTION_CONFLICT'):
        call(rig, lease_generation=2, secreto_referencias=[{'id': str(uuid4()), 'nombre': 'APP_PASSWORD', 'revision': 1}])
    assert len(rig.service.starts) == 1


@pytest.mark.parametrize('change', ['reboot', 'absent', 'exit-zero', 'replaced-unit'])
def test_unproven_unit_state_is_uncertain_and_never_reinstalled(rig, change):
    call(rig)
    unit = rig.service.units[rig.request['execution_id']]
    if change == 'reboot': rig.context.boot = str(uuid4())
    if change == 'absent': rig.service.units.clear()
    if change == 'exit-zero': unit['state'] = 'inactive'
    if change == 'replaced-unit': unit['invocation_id'] = str(uuid4())
    assert call(rig, 'status')['estado'] == 'incierto'
    assert call(rig)['estado'] == 'incierto' and len(rig.service.starts) == 1


def test_worker_can_finish_after_takeover_but_terminal_tombstone_cannot_change(rig):
    first = call(rig); call(rig, 'status', lease_generation=2)
    invocation = rig.service.units[rig.request['execution_id']]['invocation_id']
    assert rig.supervisor.claim_worker(rig.request['execution_id'], fingerprint=first['fingerprint'],
        boot_id=rig.context.boot, invocation_id=invocation)
    result = {'comprobaciones': ['aislamiento', 'runtime', 'salud', 'acceso_web'], 'recurso_configurado': True}
    rig.supervisor.complete(rig.request['execution_id'], fingerprint=first['fingerprint'],
        boot_id=rig.context.boot, invocation_id=invocation, resultado=result)
    rig.service.units.clear()
    assert call(rig, 'status', lease_generation=2)['estado'] == 'confirmado'
    assert call(rig, lease_generation=2)['resultado'] == result
    with pytest.raises(JobError, match='EXECUTION_CONFLICT'):
        rig.supervisor.complete(rig.request['execution_id'], fingerprint=first['fingerprint'],
            boot_id=rig.context.boot, invocation_id=invocation, error_codigo='NO_SPACE')
    assert len(rig.service.starts) == 1


def test_foreign_identity_or_node_never_gets_a_manifest_or_secrets(rig):
    rig.context.foreign = True
    with pytest.raises(JobError, match='IDENTITY_MISMATCH'): call(rig)
    assert rig.credentials.values == {} and rig.service.starts == []
    assert rig.store.jobs() == []
    rig.context.foreign = False; call(rig)
    with pytest.raises(JobError, match='IDENTITY_MISMATCH'): call(rig, 'status', resource_uuid=str(uuid4()))


def test_manifest_exists_before_detached_service_start_and_limit_is_two(rig):
    original_start = rig.service.start
    def inspect_before_start(execution_id, **kwargs):
        manifest = rig.store.read_job(execution_id)
        assert manifest['dispatch_state'] == 'solicitado'
        assert manifest['fingerprint'] and manifest['estado'] == 'preparado'
        return original_start(execution_id, **kwargs)
    rig.service.start = inspect_before_start
    call(rig)
    for number in (2, 3):
        request = deepcopy(rig.request)
        request.update({k: str(uuid4()) for k in ('operation_id', 'operacion_raiz_id', 'intento_id', 'execution_id', 'resource_uuid')})
        request['vmid'] += number
        if number == 2: rig.supervisor.handle(canonical(request))
        else:
            with pytest.raises(JobError, match='PROFILE_UNAVAILABLE'): rig.supervisor.handle(canonical(request))
    assert len(rig.service.starts) == 2


def test_symlinks_hardlinks_and_unknown_state_cannot_be_overwritten(rig, tmp_path):
    target = tmp_path / 'do-not-touch'; target.write_text('protected')
    name = rig.path / ('job.' + rig.request['execution_id'] + '.json')
    name.symlink_to(target)
    with pytest.raises(JobError): call(rig)
    assert target.read_text() == 'protected' and rig.service.starts == []
    name.unlink(); name.hardlink_to(target)
    with pytest.raises(JobError): call(rig)
    name.unlink(); name.write_text('{broken')
    with pytest.raises(JobError): call(rig)
    assert name.read_text() == '{broken' and rig.service.starts == []


def test_locks_are_short_nonblocking_and_units_have_no_free_commands(rig):
    with rig.store.lock('resource', rig.request['resource_uuid']):
        with pytest.raises(JobError, match='UNCONFIRMED'):
            with rig.store.lock('resource', rig.request['resource_uuid']): pass
    calls = []
    launcher = SystemdService(run_command=lambda argv, **kwargs: calls.append((argv, kwargs)) or b'')
    launcher.start(rig.request['execution_id'], timeout_seconds=2700)
    argv, kwargs = calls[0]
    assert '--property=Type=exec' in argv and '--property=Restart=no' in argv
    assert '--property=StandardOutput=null' in argv and '--property=StandardError=null' in argv
    assert not set(argv) & {'--pty', '--pipe', '--wait', '--scope', '-t', '-P'}
    assert argv[-4:] == ['/usr/bin/python3', '-I', '/opt/nap/applications/job/worker.py', rig.request['execution_id']]
    assert rig.request['secretos']['APP_PASSWORD'] not in ' '.join(argv)
    with pytest.raises(JobError): launcher.start('../escape', timeout_seconds=2700)


def test_one_operation_and_attempt_cannot_admit_a_different_resource(rig):
    call(rig)
    for preserved in ('operation_id', 'intento_id'):
        changed = deepcopy(rig.request)
        changed.update({k: str(uuid4()) for k in ('operation_id', 'intento_id', 'execution_id', 'resource_uuid') if k != preserved})
        with pytest.raises(JobError, match='EXECUTION_CONFLICT'): rig.supervisor.handle(canonical(changed))
    assert len(rig.service.starts) == 1


def test_disk_error_after_launch_never_authorizes_a_second_effect(rig, monkeypatch):
    original = rig.store.write_job
    def fail_after_effect(job):
        if job['estado'] == 'ejecutando': raise JobError('NO_SPACE')
        return original(job)
    monkeypatch.setattr(rig.store, 'write_job', fail_after_effect)
    with pytest.raises(JobError, match='NO_SPACE'): call(rig)
    monkeypatch.setattr(rig.store, 'write_job', original)
    assert call(rig, 'status')['estado'] == 'ejecutando'
    call(rig)
    assert len(rig.service.starts) == 1


def test_credential_staging_failure_is_explicit_but_never_releases_guest(rig):
    rig.credentials.fail = True
    result = call(rig)
    assert result['estado'] == 'fallido' and result['error_codigo'] == 'NO_SPACE'
    assert rig.service.starts == []
    assert len(rig.store.jobs()) == 1  # Retain tombstone and known identity.


def test_expired_profile_does_not_hide_an_existing_job(rig):
    call(rig)
    rig.supervisor.profiles = ProfileRegistry({})
    assert call(rig, 'status')['estado'] == 'ejecutando'
    assert call(rig)['estado'] == 'ejecutando'


def test_missing_technical_checks_or_foreign_guest_cannot_confirm(rig):
    first = call(rig)
    invocation = rig.service.units[rig.request['execution_id']]['invocation_id']
    assert rig.supervisor.claim_worker(rig.request['execution_id'], fingerprint=first['fingerprint'],
        boot_id=rig.context.boot, invocation_id=invocation)
    with pytest.raises(JobError):
        rig.supervisor.complete(rig.request['execution_id'], fingerprint=first['fingerprint'], boot_id=rig.context.boot, invocation_id=invocation,
            resultado={'comprobaciones': ['runtime'], 'recurso_configurado': True})
    rig.context.foreign = True
    with pytest.raises(JobError, match='IDENTITY_MISMATCH'):
        rig.supervisor.complete(rig.request['execution_id'], fingerprint=first['fingerprint'], boot_id=rig.context.boot, invocation_id=invocation,
            resultado={'comprobaciones': ['aislamiento', 'runtime', 'salud', 'acceso_web'], 'recurso_configurado': True})
    assert rig.store.read_job(rig.request['execution_id'])['estado'] == 'ejecutando'


def test_result_requires_private_worker_claim(rig):
    first = call(rig)
    with pytest.raises(JobError):
        rig.supervisor.complete(rig.request['execution_id'], fingerprint=first['fingerprint'], boot_id=rig.context.boot,
            invocation_id=rig.service.units[rig.request['execution_id']]['invocation_id'],
            resultado={'comprobaciones': ['aislamiento', 'runtime', 'salud', 'acceso_web'], 'recurso_configurado': True})


def test_closed_directory_never_falls_back_to_the_current_working_directory(rig):
    rig.store.close()
    with pytest.raises(JobError): rig.store.read_job(rig.request['execution_id'])
    with pytest.raises(JobError): rig.store.write('resource', rig.request['resource_uuid'], {})


@pytest.mark.parametrize('output,expected', [
    (b'LoadState=not-found\nActiveState=inactive\nInvocationID=\nResult=\n', 'absent'),
    (b'LoadState=loaded\nActiveState=active\nInvocationID=11111111111141118111111111111111\nResult=success\n', 'active'),
    (b'LoadState=loaded\nActiveState=failed\nInvocationID=11111111111141118111111111111111\nResult=timeout\n', 'inactive'),
])
def test_native_unit_observation_is_bounded_and_structured(output, expected):
    def run(*args, **kwargs):
        assert kwargs['accepted_codes'] == (0,1)
        return output
    service = SystemdService(run_command=run)
    result = service.observe(str(uuid4()))
    assert result['state'] == expected
    assert 'success' not in result.values()  # Exit zero is never a delivery result.
