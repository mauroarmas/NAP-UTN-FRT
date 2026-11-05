import asyncio
import json
from uuid import uuid4

import pytest


def request(action='bootstrap'):
    return {'protocol': 'nap-guest-runner/1', 'operation_id': str(uuid4()), 'action': action,
        'cluster_uuid': str(uuid4()), 'resource_uuid': str(uuid4()), 'node': 'pve1', 'vmid': 101,
        'pool': 'catedra-1', 'nonce': 'n' * 43, 'definition_key': 'linux-test', 'definition_version': '1.0.0',
        'definition_sha256': 'a' * 64, 'bundle_sha256': 'b' * 64, 'network_profile_id': 'test-network',
        'parameters': {'display_name': 'Mi servicio'}, **({'secrets': {'guest_password': 'private-test-only-value'}} if action == 'bootstrap' else {})}


@pytest.mark.parametrize('update', [{'action': 'shell'}, {'vmid': True}, {'node': '-oProxyCommand=sh'},
    {'command': 'id'}, {'path': '/tmp/bootstrap'}, {'secrets': {'root_password': 'bad'}}, {'nonce': 'short'}])
def test_runner_protocol_rejects_untrusted_actions_and_fields(update):
    from app.schemas.guest_runner import parse_request, RunnerError
    with pytest.raises(RunnerError) as exc:
        parse_request(json.dumps(request() | update).encode())
    assert exc.value.code == 'INVALID_REQUEST'


def test_runner_protocol_limits_json_and_duplicate_keys():
    from app.schemas.guest_runner import parse_request, RunnerError
    for raw in [b' ' * 65537, b'{"action":"inspect","action":"bootstrap"}', b'{"vmid":NaN}']:
        with pytest.raises(RunnerError):
            parse_request(raw)


@pytest.fixture
def runner_config(tmp_path):
    key, hosts = tmp_path / 'identity', tmp_path / 'known_hosts'
    key.write_text('fake-key-never-used'); key.chmod(0o600)
    hosts.write_text('pve-test.invalid ssh-ed25519 TEST-ONLY'); hosts.chmod(0o644)
    return {'pve1': {'host': 'pve-test.invalid', 'user': 'naprunner', 'port': 22,
        'private_key_path': str(key), 'known_hosts_path': str(hosts)}}


async def test_ssh_uses_pinned_hostkeys_and_stdin_without_secrets_in_arguments(runner_config, caplog):
    from app.services.guest_runner_client import GuestRunnerClient
    from app.utils.clock import clock
    value = request()
    captured = {}
    class Process:
        returncode = 0
        async def communicate(self, input=None):
            captured['input'] = input
            return json.dumps({'protocol': value['protocol'], 'operation_id': value['operation_id'],
                'action': value['action'], 'resource_uuid': value['resource_uuid'], 'status': 'succeeded',
                'phase': 'verified', 'observed_at': clock.now().isoformat(), 'identity_verified': True,
                'result': {'ready': True}}).encode(), b''
    async def start(*args, **kwargs):
        captured['argv'], captured['options'] = args, kwargs
        return Process()
    response = await GuestRunnerClient(config=runner_config, start_process=start).execute(value)
    assert response['status'] == 'succeeded'
    args = captured['argv']
    assert 'StrictHostKeyChecking=yes' in args and 'IdentitiesOnly=yes' in args and 'BatchMode=yes' in args
    assert '-F' in args and '/dev/null' in args and '-T' in args
    assert any(arg.startswith('UserKnownHostsFile=') for arg in args)
    assert 'private-test-only-value' not in repr(args) + caplog.text
    assert json.loads(captured['input'])['secrets'] == value['secrets']
    assert captured['options'].get('shell') is not True


async def test_changed_hostkey_is_a_safe_failure_without_remote_stderr(runner_config, caplog):
    from app.services.guest_runner_client import GuestRunnerClient
    from app.schemas.guest_runner import RunnerError
    class Process:
        returncode = 255
        async def communicate(self, input=None):
            return b'', b'HOST KEY CHANGED private-test-only-value'
    async def start(*args, **kwargs):
        return Process()
    with pytest.raises(RunnerError) as exc:
        await GuestRunnerClient(config=runner_config, start_process=start).execute(request())
    assert exc.value.code in {'RUNNER_UNAVAILABLE', 'UNCONFIRMED'}
    assert 'private-test-only-value' not in str(exc.value) + caplog.text


async def test_response_for_another_instance_or_with_secrets_is_rejected(runner_config):
    from app.services.guest_runner_client import GuestRunnerClient
    from app.schemas.guest_runner import RunnerError
    value = request('inspect')
    class Process:
        returncode = 0
        async def communicate(self, input=None):
            return json.dumps({'protocol': value['protocol'], 'operation_id': value['operation_id'],
                'action': 'inspect', 'resource_uuid': str(uuid4()), 'status': 'succeeded', 'phase': 'verified',
                'identity_verified': True, 'observed_at': '2026-10-20T00:00:00Z', 'result': {'password': 'secret'}}).encode(), b''
    async def start(*args, **kwargs):
        return Process()
    with pytest.raises(RunnerError):
        await GuestRunnerClient(config=runner_config, start_process=start).execute(value)


async def test_invalid_ssh_destination_and_unsafe_key_never_start_a_process(runner_config):
    from app.services.guest_runner_client import GuestRunnerClient
    from app.schemas.guest_runner import RunnerError
    calls = []
    async def start(*args, **kwargs):
        calls.append(args)
        raise AssertionError('must not start')
    entry = runner_config['pve1']
    original = entry['host']
    entry['host'] = '-oProxyCommand=sh'
    with pytest.raises(RunnerError):
        await GuestRunnerClient(config=runner_config, start_process=start).execute(request())
    entry['host'] = original
    from pathlib import Path
    Path(entry['private_key_path']).chmod(0o644)
    with pytest.raises(RunnerError):
        await GuestRunnerClient(config=runner_config, start_process=start).execute(request())
    assert not calls


async def test_deadline_stops_local_transport_and_keeps_result_unconfirmed(runner_config):
    from app.services.guest_runner_client import GuestRunnerClient
    from app.schemas.guest_runner import RunnerError
    class Process:
        returncode = None
        stopped = False
        async def communicate(self, input=None):
            await asyncio.Event().wait()
        def kill(self):
            self.stopped = True
        async def wait(self):
            self.returncode = -9
    process = Process()
    async def start(*args, **kwargs):
        return process
    with pytest.raises(RunnerError) as exc:
        await GuestRunnerClient(config=runner_config, start_process=start, timeout_seconds=0.02).execute(request())
    assert exc.value.code == 'UNCONFIRMED' and process.stopped


async def test_valid_identity_does_not_allow_secret_fields_in_response(runner_config):
    from app.services.guest_runner_client import GuestRunnerClient
    from app.schemas.guest_runner import RunnerError
    from app.utils.clock import clock
    value = request()
    class Process:
        returncode = 0
        async def communicate(self, input=None):
            return json.dumps({**{key: value[key] for key in ['protocol', 'operation_id', 'action', 'resource_uuid']},
                'status': 'succeeded', 'phase': 'verified', 'observed_at': clock.now().isoformat(),
                'identity_verified': True, 'result': {'ready': True, 'password': 'private'}}).encode(), b''
    async def start(*args, **kwargs):
        return Process()
    with pytest.raises(RunnerError):
        await GuestRunnerClient(config=runner_config, start_process=start).execute(value)
