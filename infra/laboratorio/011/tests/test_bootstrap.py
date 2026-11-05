import importlib.util
import json
from pathlib import Path

import pytest
from uuid import uuid4


ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('bootstrap011', ROOT / 'preparar_entorno.py')
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


def test_common_package_plan_has_no_effect_and_stays_separate_from_initial_bootstrap(tmp_path):
    source = ROOT.parents[2]
    root = tmp_path/'node'; root.mkdir(mode=0o700)
    cold = {'schema_version':'nap-application-node/1','cluster_uuid':str(uuid4()),'node':'proxmox','profiles':{}}
    result = bootstrap.install_common_package(source, cold, root=root)
    assert result['state'] == 'plan' and result['profiles_enabled_by_install'] == []
    assert not (root/'opt').exists()


def candidate():
    return json.loads((ROOT / 'candidatos.json').read_text())


def config():
    return {'schema_version': 'nap-lab-bootstrap/1', 'registry': {
        'endpoint': 'https://172.16.36.1:5443', 'ca_pem': 'fixture-public-ca',
        'username': 'nap011reader', 'password': 'secret-not-for-receipt'},
        'network': {'cidr': '172.16.36.0/24', 'bridge': 'vmbr0', 'gateway': '172.16.36.2',
                    'slots': [{'address': '172.16.36.81', 'mac': '02:11:00:00:00:81',
                               'host': 'app1.nap011.test'}]}}


def inventory(_):
    return {'schema_version': 'nap-node-preflight/1', 'read_only': True, 'node': 'proxmox',
            'tools': {k: True for k in ('python3', 'pct', 'systemd', 'nft')},
            'apparmor_enabled': True, 'available_bytes': 50 * 1024**3,
            'templates': {p['base']: p['base_sha256'] or 'a' * 64 for p in candidate()['profiles']}}


def test_plan_has_no_effects_or_credentials(tmp_path):
    root = tmp_path / 'system'
    report = bootstrap.prepare_node(candidate(), config(), root=root, inventory_provider=inventory)
    assert not root.exists()
    assert 'secret-not-for-receipt' not in json.dumps(report)
    assert report['profiles_enabled'] == []


def test_apply_is_idempotent_and_does_not_persist_registry_password(tmp_path):
    root = tmp_path / 'system'
    args = dict(root=root, inventory_provider=inventory, registry_verifier=lambda _: True)
    first = bootstrap.prepare_node(candidate(), config(), apply=True, **args)
    snapshot = {p: (p.stat().st_ino, p.read_bytes()) for p in root.rglob('*') if p.is_file()}
    def changed_free_space(value):
        result = inventory(value)
        result['available_bytes'] -= 1024**2
        return result
    second = bootstrap.prepare_node(candidate(), config(), apply=True,
        **{**args, 'inventory_provider': changed_free_space})
    assert first['state'] == 'node_bootstrap_staged'
    assert second['state'] == 'node_bootstrap_already_staged'
    assert snapshot == {p: (p.stat().st_ino, p.read_bytes()) for p in snapshot}
    assert not any(b'secret-not-for-receipt' in p.read_bytes() for p in snapshot)


def test_unexpected_existing_file_is_not_overwritten(tmp_path):
    root = tmp_path / 'system'
    dest = root / 'etc/nap/applications-011'
    dest.mkdir(parents=True, mode=0o700)
    for parent in (root, root / 'etc', root / 'etc/nap'):
        parent.chmod(0o700)
    (dest / 'network.json').write_text('unrelated')
    (dest / 'network.json').chmod(0o600)
    with pytest.raises(ValueError, match='EXISTING_FILE_DIFFERS'):
        bootstrap.prepare_node(candidate(), config(), root=root, apply=True,
                               inventory_provider=inventory, registry_verifier=lambda _: True)
    assert (dest / 'network.json').read_text() == 'unrelated'
    assert not (dest / 'ca.crt').exists()


@pytest.mark.parametrize('change', ['registry', 'management_ip', 'duplicate', 'legacy_range'])
def test_input_cannot_point_to_other_hosts_or_legacy_slots(change):
    value = config()
    if change == 'registry': value['registry']['endpoint'] = 'https://127.0.0.1:8001'
    elif change == 'management_ip': value['network']['slots'][0]['address'] = '172.16.36.100'
    elif change == 'duplicate': value['network']['slots'] *= 2
    else: value['network']['slots'][0]['address'] = '172.16.36.61'
    with pytest.raises(ValueError):
        bootstrap.validate_config(candidate(), value)


def test_tls_failure_never_stages_node_files(tmp_path):
    root = tmp_path / 'system'
    with pytest.raises(ValueError, match='REGISTRY_NOT_CONFIRMED'):
        bootstrap.prepare_node(candidate(), config(), root=root, apply=True,
                               inventory_provider=inventory, registry_verifier=lambda _: False)
    assert not root.exists()


def test_disk_failure_removes_only_files_created_by_this_attempt(tmp_path, monkeypatch):
    root = tmp_path / 'system'
    original = bootstrap.os.open
    def fail(path, flags, *args, **kwargs):
        if Path(path).name == 'network.json' and flags & bootstrap.os.O_WRONLY:
            raise OSError('No space fixture')
        return original(path, flags, *args, **kwargs)
    monkeypatch.setattr(bootstrap.os, 'open', fail)
    with pytest.raises(OSError):
        bootstrap.prepare_node(candidate(), config(), apply=True, root=root,
            inventory_provider=inventory, registry_verifier=lambda _: True)
    dest = root / 'etc/nap/applications-011'
    assert list(dest.iterdir()) == [dest / '.lock']
