import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('preflight011', ROOT / 'preflight.py')
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


def manifest():
    return json.loads((ROOT / 'candidatos.json').read_text())


def inventory():
    return {'schema_version': 'nap-node-preflight/1', 'read_only': True,
            'node': 'proxmox', 'tools': {k: True for k in ['python3', 'pct', 'systemd', 'nft']},
            'apparmor_enabled': True, 'available_bytes': 50 * 1024**3,
            'templates': {p['base']: 'a' * 64 for p in manifest()['profiles']}}


def test_candidate_inventory_never_enables_profile():
    report = preflight.evaluate(manifest(), inventory())
    assert report['read_only'] is True
    assert report['environment'] == 'laboratorio_local'
    assert report['node_prerequisites_ok'] is True
    assert report['ready_for_spikes'] is False  # Falta bootstrap/red/registry y gate real.
    assert report['profiles_enabled'] == []
    assert all(p['state'] == 'pendiente_validacion' for p in report['profiles'])
    assert 'REAL_GATES_REQUIRED' in report['blockers']


def test_missing_facts_block_and_do_not_leak_private_diagnostic():
    data = {'secret': 'do-not-copy', 'estado': 'diagnostico_completado', 'sin_modificaciones': True}
    report = preflight.evaluate(manifest(), data)
    assert report['ready_for_spikes'] is False
    assert 'NODE_INVENTORY_REQUIRED' in report['blockers']
    assert 'do-not-copy' not in json.dumps(report)


def test_changed_base_hash_and_disabled_apparmor_block_spikes():
    value = manifest()
    value['profiles'][0]['base_sha256'] = 'b' * 64
    data = inventory()
    data['apparmor_enabled'] = False
    report = preflight.evaluate(value, data)
    assert not report['ready_for_spikes']
    assert 'APPARMOR_NOT_CONFIRMED' in report['blockers']
    assert 'BASE_HASH_MISMATCH' in report['blockers']


@pytest.mark.parametrize('change', ['profile', 'path', 'size', 'unknown'])
def test_manifest_cannot_enable_profiles_or_select_arbitrary_files(change):
    value = manifest()
    if change == 'profile': value['profiles'][0]['state'] = 'habilitado'
    elif change == 'path': value['profiles'][0]['base'] = '../../etc/shadow'
    elif change == 'size': value['sizes']['medium']['ram_mb'] = 4096
    else: value['command'] = 'arbitrary command'
    with pytest.raises(ValueError):
        preflight.evaluate(value, inventory())


def test_json_reader_refuses_links_writable_files_and_duplicate_keys(tmp_path):
    source = tmp_path / 'source.json'
    source.write_text('{"a":1}')
    source.chmod(0o600)
    link = tmp_path / 'link.json'
    link.symlink_to(source)
    with pytest.raises(OSError):
        preflight.read_json(link)
    source.chmod(0o666)
    with pytest.raises(ValueError):
        preflight.read_json(source)
    source.chmod(0o600)
    source.write_text('{"a":1,"a":2}')
    with pytest.raises(ValueError, match='DUPLICATE_KEY'):
        preflight.read_json(source)
