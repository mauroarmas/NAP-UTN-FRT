import hashlib
import json

import pytest

from tests.test_guest_runner_client import request


@pytest.fixture
def node_case(tmp_path):
    from infra.runner.node_executor import NodeExecutor
    from infra.services.build_image import make_recipe_bundle
    value = request()
    bundle = tmp_path / 'recipe.tar.gz'
    make_recipe_bundle('linux', bundle); bundle.chmod(0o444)
    value['bundle_sha256'] = hashlib.sha256(bundle.read_bytes()).hexdigest()
    entry = {'product': 'linux', 'cluster_uuid': value['cluster_uuid'], 'nodes': ['pve1'],
        'definition_sha256': value['definition_sha256'], 'bundle_sha256': value['bundle_sha256'],
        'bundle_path': str(bundle), 'network_profile_ids': ['test-network'],
        'networks': {'test-network': {'subnets': ['10.50.0.0/24']}}}
    registry = {value['definition_key'] + ':' + value['definition_version']: entry}
    class Commands:
        calls = []
        foreign = False
        change_after_exec = False
        def __call__(self, argv, *, input=None, **kwargs):
            self.calls.append((list(argv), input))
            if argv[0] == '/usr/bin/pvesh':
                if '/cluster/resources' in argv:
                    return json.dumps([{'vmid': value['vmid'], 'node': 'pve1', 'pool': value['pool'], 'type': 'lxc', 'cpu': 0.0125}]).encode()
                marker = {key: value[key] for key in ['cluster_uuid', 'resource_uuid', 'pool', 'definition_sha256', 'bundle_sha256']}
                marker['nonce_sha256'] = hashlib.sha256(value['nonce'].encode()).hexdigest()
                if self.foreign:
                    marker['resource_uuid'] = 'foreign'
                return json.dumps({'unprivileged': 1, 'description': json.dumps({'nap': marker})}).encode()
            if argv[0] == '/usr/sbin/pct' and 'exec' in argv:
                if '/usr/sbin/ip' in argv:
                    return b'[{"addr_info":[{"family":"inet","local":"10.50.0.101"}]}]'
                if input:
                    parsed = json.loads(input)
                    assert parsed['request']['action'] in {'bootstrap', 'inspect', 'verify'}
                    return b'{"ready":true,"bootstrap_completed":true,"username":"napadmin"}'
                if self.change_after_exec:
                    self.foreign = True
            return b''
    commands = Commands()
    executor = NodeExecutor(registry=registry, run_command=commands, local_node='pve1', temporary_root=tmp_path / 'private')
    return executor, commands, value, bundle


def test_node_executes_only_fixed_commands_and_keeps_secret_in_stdin(node_case):
    executor, commands, value, bundle = node_case
    result = executor.execute(value, bundle_path=str(bundle))
    assert result['ready']
    assert value['secrets']['guest_password'] not in repr([args for args, _ in commands.calls])
    assert any(input and value['secrets']['guest_password'] in input.decode() for _, input in commands.calls)
    for index, (argv, _) in enumerate(commands.calls):
        if argv[0] == '/usr/sbin/pct':
            # Comprobación externa inmediatamente antes y después de cada
            # push/exec, sin adoptar una observación anterior de propiedad.
            assert commands.calls[index - 1][0][0] == '/usr/bin/pvesh'
            assert commands.calls[index + 1][0][0] == '/usr/bin/pvesh'
    assert not list(executor.temporary_root.iterdir())


def test_node_stops_after_identity_changes_before_push(node_case):
    from app.schemas.guest_runner import RunnerError
    executor, commands, value, bundle = node_case
    commands.change_after_exec = True
    with pytest.raises(RunnerError) as exc:
        executor.execute(value, bundle_path=str(bundle))
    assert exc.value.code == 'IDENTITY_MISMATCH'
    assert not any('push' in argv for argv, _ in commands.calls)
