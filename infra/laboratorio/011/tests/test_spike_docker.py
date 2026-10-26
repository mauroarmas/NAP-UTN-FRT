import importlib.util
import json
import os
import stat
import sys
from pathlib import Path
from uuid import uuid4

import pytest


ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('docker_spike011', ROOT / 'spike_docker.py')
spike = importlib.util.module_from_spec(spec)
spec.loader.exec_module(spike)


def marker():
    return {'purpose': 'nap011-docker-spike', 'run_id': str(uuid4())}


class Node:
    def __init__(self):
        self.resource = None
        self.firewall = False
        self.events = []
        self.lose_create = False
        self.fail_cleanup = False

    def require_prerequisites(self): self.events.append('prerequisites')
    def config(self): return self.resource
    def create(self, expected):
        self.events.append('create'); self.resource = {'marker': expected, 'unprivileged': 1}
        if self.lose_create: raise TimeoutError('Respuesta perdida')
    def install_firewall(self, expected): self.events.append('firewall'); self.firewall = True
    def configure_features(self, expected): self.events.append('features')
    def start(self, expected):
        assert self.firewall, 'No arrancar un guest sin aislamiento externo'
        self.events.append('start')
    def probe(self, expected): self.events.append('probe'); return {'private_pull': True}
    def cleanup(self, expected):
        assert self.resource is None or self.resource['marker'] == expected
        self.events.append('cleanup')
        if self.fail_cleanup: raise OSError('Fallo de infraestructura')
        self.resource = None
    def absent(self): return self.resource is None
    def remove_firewall(self, expected):
        assert self.absent()
        self.events.append('remove_firewall'); self.firewall = False


def test_probe_installs_guard_before_start_and_confirms_absence(tmp_path):
    node = Node(); expected = marker(); journal = tmp_path / 'state.json'
    result = spike.execute_probe(node, expected, journal)
    assert result['state'] == 'probe_passed' and result['resource_absent'] is True
    assert node.events.index('firewall') < node.events.index('start')
    before = list(node.events)
    assert spike.execute_probe(node, expected, journal) == result
    assert node.events == before  # Replay terminal no ejecuta nada nuevo.


def test_response_lost_after_create_never_creates_twice(tmp_path):
    node = Node(); node.lose_create = True
    result = spike.execute_probe(node, marker(), tmp_path / 'state.json')
    assert result['state'] == 'probe_failed' and result['resource_absent'] is True
    assert node.events.count('create') == 1 and node.resource is None


def test_foreign_resource_is_never_stopped_or_deleted(tmp_path):
    node = Node(); node.resource = {'marker': marker(), 'unprivileged': 1}
    result = spike.execute_probe(node, marker(), tmp_path / 'state.json')
    assert result['state'] == 'probe_blocked'
    assert 'create' not in node.events and 'cleanup' not in node.events


def test_cleanup_failure_retains_resource_and_firewall(tmp_path):
    node = Node(); node.fail_cleanup = True
    result = spike.execute_probe(node, marker(), tmp_path / 'state.json')
    assert result['state'] == 'cleanup_pending' and result['resource_absent'] is False
    assert node.resource is not None and node.firewall


def test_interrupted_probe_can_only_clean_owned_resource(tmp_path):
    node = Node(); expected = marker(); journal = tmp_path / 'state.json'
    spike.save(journal, {'marker': expected, 'fingerprint': None, 'phase': 'probing', 'vmid': spike.VMID})
    node.resource = {'marker': expected, 'unprivileged': 1}; node.firewall = True
    with pytest.raises(ValueError, match='RECONCILIATION_REQUIRED'):
        spike.execute_probe(node, expected, journal)
    result = spike.reconcile_probe(node, expected, journal)
    assert result['state'] == 'probe_cleaned' and result['resource_absent']
    assert 'create' not in node.events and 'start' not in node.events
    assert not node.firewall
    assert json.loads(journal.read_text())['result'] == result


def test_reconciliation_refuses_foreign_resource(tmp_path):
    node = Node(); expected = marker(); journal = tmp_path / 'state.json'
    spike.save(journal, {'marker': expected, 'fingerprint': None, 'phase': 'creating', 'vmid': spike.VMID})
    node.resource = {'marker': marker(), 'unprivileged': 1}
    result = spike.reconcile_probe(node, expected, journal)
    assert result['state'] == 'cleanup_pending'
    assert 'cleanup' not in node.events and 'remove_firewall' not in node.events


def test_bridge_policy_is_scoped_to_probe_and_rejects_injection():
    expected = marker()
    rules = spike.firewall_policy(expected, '172.16.36.81', '02:11:00:00:00:51')
    assert 'veth900011i0' in rules
    assert 'hook input' in rules and 'hook output' in rules and 'hook forward' in rules
    assert '172.16.36.1 tcp dport 5443 accept' in rules
    assert '172.16.0.0/12' in rules
    assert 'flush ruleset' not in rules
    with pytest.raises(ValueError):
        spike.firewall_policy(expected, '172.16.36.100', '02:11:00:00:00:51')
    with pytest.raises(ValueError):
        spike.firewall_policy(expected, '172.16.36.81', 'bad; flush ruleset')


@pytest.mark.integration
def test_pct_directory_umask_does_not_weaken_private_state(tmp_path):
    original = os.umask(0o077)
    try:
        parent = tmp_path / 'pct'
        # La reproducción pasa por un subproceso, como la creación real de PVE.
        spike.command([sys.executable, '-c', 'import os,sys;os.mkdir(sys.argv[1])', str(parent)],
                      child_umask=0o022)
        assert stat.S_IMODE(parent.stat().st_mode) == 0o755
        journal = tmp_path / 'private.json'; spike.save(journal, {'state': 'fixture'})
        assert stat.S_IMODE(journal.stat().st_mode) == 0o600
        private = tmp_path / 'private-directory'; private.mkdir()
        assert stat.S_IMODE(private.stat().st_mode) == 0o700
    finally:
        os.umask(original)


def test_retire_only_empty_workspace_of_completed_failed_probe(tmp_path):
    node = Node(); expected = marker(); journal = tmp_path / 'state.json'
    spike.save(journal, {'marker': expected, 'fingerprint': None, 'phase': 'creating', 'vmid': spike.VMID,
                        'result': {'state': 'probe_failed', 'resource_absent': True}})
    root = tmp_path / 'host'; workspace = root / f'var/lib/lxc/{spike.VMID}'
    (workspace / 'rootfs').mkdir(parents=True, mode=0o700)
    spike.retire_failed_workspace(node, expected, journal, root=root)
    assert not workspace.exists()
    assert 'create' not in node.events


def test_retire_workspace_refuses_content_live_resource_and_links(tmp_path):
    node = Node(); expected = marker(); journal = tmp_path / 'state.json'
    spike.save(journal, {'marker': expected, 'fingerprint': None, 'phase': 'creating', 'vmid': spike.VMID,
                        'result': {'state': 'probe_failed', 'resource_absent': True}})
    root = tmp_path / 'host'; workspace = root / f'var/lib/lxc/{spike.VMID}'
    (workspace / 'rootfs').mkdir(parents=True)
    (workspace / 'rootfs/foreign').write_text('conservar')
    with pytest.raises(ValueError): spike.retire_failed_workspace(node, expected, journal, root=root)
    assert (workspace / 'rootfs/foreign').read_text() == 'conservar'
    (workspace / 'rootfs/foreign').unlink()
    node.resource = {'marker': marker()}
    with pytest.raises(ValueError): spike.retire_failed_workspace(node, expected, journal, root=root)
    assert workspace.exists()
    node.resource = None
    (workspace / 'rootfs').rmdir()
    (workspace / 'rootfs').symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError): spike.retire_failed_workspace(node, expected, journal, root=root)
    assert (workspace / 'rootfs').is_symlink()
