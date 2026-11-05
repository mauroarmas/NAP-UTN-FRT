from copy import deepcopy
import hashlib
import json

import pytest

from tests.test_guest_runner_client import request


@pytest.fixture
def runner_case(tmp_path):
    from infra.runner.nap_guest_runner import Runner
    value = request()
    bundle = tmp_path / 'linux-v1.py'
    bundle.write_bytes(b'# controlled recipe test double\n')
    bundle.chmod(0o444)
    value['bundle_sha256'] = hashlib.sha256(bundle.read_bytes()).hexdigest()
    registry = {value['definition_key'] + ':' + value['definition_version']: {
        'product': 'linux', 'definition_sha256': value['definition_sha256'],
        'bundle_sha256': value['bundle_sha256'], 'bundle_path': str(bundle), 'nodes': ['pve1'],
        'cluster_uuid': value['cluster_uuid'], 'network_profile_ids': ['test-network']}}
    class Node:
        calls = 0
        completed = False
        mismatch = False
        fail_after_effect = False
        def inspect(self, candidate):
            return {**{key: value[key] for key in ['cluster_uuid', 'resource_uuid', 'node', 'vmid', 'pool', 'nonce', 'definition_sha256', 'bundle_sha256']},
                'resource_uuid': 'foreign' if self.mismatch else value['resource_uuid'],
                'unprivileged': True, 'type': 'lxc', 'bootstrap_completed': self.completed,
                'ready': self.completed}
        def execute(self, candidate, *, bundle_path):
            self.calls += 1; self.completed = True
            if self.fail_after_effect:
                raise TimeoutError('secret must never be returned')
            return {'ready': True}
    node = Node()
    state = tmp_path / 'state'
    return Runner(state_dir=state, registry=registry, executor=node), node, value, registry, bundle


@pytest.mark.parametrize('field', ['resource_uuid', 'pool', 'nonce', 'definition_sha256', 'bundle_sha256'])
def test_ownership_or_recipe_mismatch_never_executes(runner_case, field):
    runner, node, value, _, _ = runner_case
    wrong = deepcopy(value)
    wrong[field] = 'c' * 64 if field.endswith('sha256') else 'other-value'
    result = runner.handle(json.dumps(wrong).encode())
    assert result['status'] == 'failed' and node.calls == 0
    assert result['identity_verified'] is False


def test_retry_and_restart_preserve_bootstrap_without_regenerating_secrets(runner_case):
    from infra.runner.nap_guest_runner import Runner
    runner, node, value, registry, _ = runner_case
    first = runner.handle(json.dumps(value).encode())
    assert first['status'] == 'succeeded'
    restarted = Runner(state_dir=runner.state_dir, registry=registry, executor=node)
    assert restarted.handle(json.dumps(value).encode())['status'] == 'succeeded' and node.calls == 1
    wrong = deepcopy(value); wrong['secrets']['guest_password'] = 'different-secret'
    assert restarted.handle(json.dumps(wrong).encode())['error']['code'] == 'IDEMPOTENCY_CONFLICT'
    assert node.calls == 1


def test_lost_response_is_inspected_before_retry_and_never_runs_twice(runner_case):
    runner, node, value, _, _ = runner_case
    node.fail_after_effect = True
    assert runner.handle(json.dumps(value).encode())['status'] == 'unconfirmed'
    assert runner.handle(json.dumps(value).encode())['status'] == 'succeeded'
    assert node.calls == 1


def test_bundle_symlink_or_changed_digest_is_rejected(runner_case, tmp_path):
    runner, node, value, registry, bundle = runner_case
    original = bundle.read_bytes()
    bundle.chmod(0o600)
    bundle.write_bytes(b'tampered')
    bundle.chmod(0o444)
    assert runner.handle(json.dumps(value).encode())['status'] == 'failed' and node.calls == 0
    bundle.unlink()
    target = tmp_path / 'outside'; target.write_bytes(original)
    bundle.symlink_to(target)
    assert runner.handle(json.dumps(value).encode())['status'] == 'failed' and node.calls == 0


def test_identity_is_rechecked_after_guest_action(runner_case):
    runner, node, value, _, _ = runner_case
    original = node.execute
    def change_identity(*args, **kwargs):
        result = original(*args, **kwargs)
        node.mismatch = True
        return result
    node.execute = change_identity
    response = runner.handle(json.dumps(value).encode())
    assert response['status'] == 'unconfirmed' and not response['identity_verified']
    assert 'private-test-only-value' not in json.dumps(response)


def test_completed_guest_without_host_history_is_not_adopted(runner_case):
    runner, node, value, _, _ = runner_case
    node.completed = True
    result = runner.handle(json.dumps(value).encode())
    assert result['status'] == 'unconfirmed' and node.calls == 0


def test_host_state_never_contains_raw_nonce_or_password(runner_case):
    runner, _, value, _, _ = runner_case
    assert runner.handle(json.dumps(value).encode())['status'] == 'succeeded'
    for path in runner.state_dir.glob('*.json'):
        text = path.read_text()
        assert value['nonce'] not in text and value['secrets']['guest_password'] not in text


def test_concurrent_new_operation_cannot_start_another_bootstrap(runner_case):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from uuid import uuid4
    from infra.runner.nap_guest_runner import Runner
    runner, node, value, registry, _ = runner_case
    started, release = Event(), Event()
    original = node.execute
    def held(*args, **kwargs):
        started.set()
        assert release.wait(3)
        return original(*args, **kwargs)
    node.execute = held
    with ThreadPoolExecutor(max_workers=1) as threads:
        future = threads.submit(runner.handle, json.dumps(value).encode())
        try:
            assert started.wait(2)
            other = Runner(state_dir=runner.state_dir, registry=registry, executor=node)
            response = other.handle(json.dumps(value | {'operation_id': str(uuid4())}).encode())
            assert response['status'] == 'unconfirmed' and node.calls == 0
        finally:
            release.set()
        assert future.result(timeout=2)['status'] == 'succeeded'
    assert node.calls == 1
