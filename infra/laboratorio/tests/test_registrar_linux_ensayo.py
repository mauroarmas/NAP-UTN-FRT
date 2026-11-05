import hashlib
import json
import os

import pytest

from infra.laboratorio import registrar_linux_ensayo as setup


@pytest.fixture
def case(tmp_path):
    paths = {
        'bundle': tmp_path/'opt/nap/recipes'/('nap009-linux-1.0.0-'+hashlib.sha256(b'fixture-bundle').hexdigest()+'.tar.gz'),
        'image': tmp_path/'var/lib/vz/template/cache/nap009-linux-1.0.0.tar.gz',
        'registry': tmp_path/'etc/nap/runner/registry.json',
    }
    for key, path in paths.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes({'bundle': b'fixture-bundle', 'image': b'fixture-image', 'registry': b'{}\n'}[key])
        path.chmod(0o600 if key == 'registry' else 0o444)
    for directory in tmp_path.rglob('*'):
        if directory.is_dir(): directory.chmod(0o755)
    (tmp_path/'root').mkdir(mode=0o700)
    plan = {'schema_version': 1, 'previous_sha256': hashlib.sha256(b'{}\n').hexdigest(),
        'definition_sha256': 'd'*64, 'cluster_uuid': '0834fb88-0a09-4b5c-8023-211bd80747d9',
        'bundle_sha256': hashlib.sha256(b'fixture-bundle').hexdigest(),
        'image_sha256': hashlib.sha256(b'fixture-image').hexdigest()}
    return tmp_path, paths, plan


def test_plan_is_readonly_and_apply_is_idempotent(case):
    root, paths, plan = case
    before = set(root.rglob('*'))
    result = setup.install(plan, root=root)
    assert result['estado'] == 'plan_sin_cambios' and set(root.rglob('*')) == before
    result = setup.install(plan, root=root, apply=True)
    assert result['estado'] == 'linux_staging_registrado'
    registry = json.loads(paths['registry'].read_text())
    assert registry == setup.registry_value(plan)
    assert registry['linux-lab-009:1.0.0']['networks'] == {'lab-vmnet8': {'subnets': ['172.16.36.0/24']}}
    assert paths['registry'].stat().st_mode & 0o777 == 0o600
    backup = setup.Path(result['respaldo_root'])
    assert backup.stat().st_mode & 0o777 == 0o600 and backup.read_bytes() == b'{}\n'
    inode = paths['registry'].stat().st_ino
    assert setup.install(plan, root=root, apply=True)['ya_existia']
    assert paths['registry'].stat().st_ino == inode


@pytest.mark.parametrize('changed', ['bundle', 'image', 'registry'])
def test_changed_artifact_or_registry_blocks_replacement(case, changed):
    root, paths, plan = case
    paths[changed].chmod(0o600); paths[changed].write_bytes(b'changed')
    before = paths['registry'].read_bytes()
    with pytest.raises(ValueError): setup.install(plan, root=root, apply=True)
    assert paths['registry'].read_bytes() == before and not list((root/'root').iterdir())


@pytest.mark.parametrize('kind', ['symlink', 'hardlink', 'writable'])
def test_untrusted_files_are_rejected(case, kind):
    root, paths, plan = case; path = paths['bundle']
    if kind == 'symlink':
        actual = path.with_suffix('.original'); path.rename(actual); path.symlink_to(actual)
    elif kind == 'hardlink': os.link(path, path.with_suffix('.other'))
    else: path.chmod(0o666)
    with pytest.raises((ValueError, OSError)): setup.install(plan, root=root, apply=True)
    assert paths['registry'].read_bytes() == b'{}\n'


def test_plan_cannot_choose_commands_paths_or_another_product(case):
    root, _, plan = case
    with pytest.raises(ValueError): setup.install({**plan, 'bundle_path': '/etc/shadow'}, root=root, apply=True)
    with pytest.raises(ValueError): setup.install({**plan, 'product': 'bookstack'}, root=root, apply=True)


def test_replace_failure_preserves_previous_registry_and_backup(case, monkeypatch):
    root, paths, plan = case
    def fail(*args): raise OSError('fixture replace failure')
    monkeypatch.setattr(setup.os, 'replace', fail)
    with pytest.raises(OSError): setup.install(plan, root=root, apply=True)
    assert paths['registry'].read_bytes() == b'{}\n'
    assert len(list((root/'root').glob('nap009-registro-respaldo-*/registry.json'))) == 1
    assert not list(paths['registry'].parent.glob('.nap009-registry-*'))


def test_lock_symlink_is_not_followed(case):
    root, paths, plan = case
    target = root/'private'; target.write_text('keep'); target.chmod(0o600)
    (paths['registry'].parent/'registry.json.lock').symlink_to(target)
    with pytest.raises(OSError): setup.install(plan, root=root, apply=True)
    assert target.read_text() == 'keep' and paths['registry'].read_bytes() == b'{}\n'
    assert not list((root/'root').iterdir())


def test_cli_refuses_non_root_before_any_filesystem_mutation(case, monkeypatch):
    root, paths, _ = case
    before = set(root.rglob('*'))
    monkeypatch.setattr(setup.os, 'geteuid', lambda: 1000)
    monkeypatch.setattr('sys.argv', ['setup', '--plan-b64', 'e30=', '--plan-sha256', '0'*64, '--apply'])
    with pytest.raises(SystemExit) as exc: setup.main()
    assert exc.value.code == 2 and set(root.rglob('*')) == before
    assert paths['registry'].read_bytes() == b'{}\n'
