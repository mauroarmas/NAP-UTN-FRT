import hashlib
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('community_spike011', ROOT / 'spike_community.py')
community = importlib.util.module_from_spec(spec)
spec.loader.exec_module(community)


@pytest.fixture
def bundle(tmp_path):
    files = {}
    for name in community.SOURCE_FILES:
        path = tmp_path / name; path.parent.mkdir(parents=True, exist_ok=True)
        data = ('# fixture ' + name).encode(); path.write_bytes(data); path.chmod(0o600)
        files[name] = hashlib.sha256(data).hexdigest()
    for directory in tmp_path.rglob('*'):
        if directory.is_dir(): directory.chmod(0o700)
    lock = {'schema_version': 'nap-community-sources/1',
            'core_commit': community.CORE_COMMIT, 'scripts_commit': community.SCRIPTS_COMMIT,
            'sources': files}
    return tmp_path, lock


def test_complete_local_bundle_is_verified_without_network(bundle):
    root, lock = bundle
    result = community.verify_sources(root, lock)
    assert set(result) == set(community.SOURCE_FILES)
    assert all(isinstance(content, bytes) for content in result.values())


@pytest.mark.parametrize('path', ['proxmox/ct/mariadb.sh', 'core/core/build.func',
                                'core/pve/backend.func', '../outside', '/etc/shadow'])
def test_host_wrappers_and_undeclared_files_are_rejected(bundle, path):
    root, lock = bundle; lock['sources'][path] = '0' * 64
    with pytest.raises(ValueError, match='SOURCE_CLOSURE'): community.verify_sources(root, lock)


def test_missing_helper_and_tampered_source_never_fall_back_to_network(bundle):
    root, lock = bundle
    path = root / 'core/lib/tools.func'; original = path.read_bytes(); path.write_bytes(b'changed')
    with pytest.raises(ValueError, match='SOURCE_HASH'): community.verify_sources(root, lock)
    path.write_bytes(original); path.unlink()
    with pytest.raises(ValueError, match='SOURCE_MISSING'): community.verify_sources(root, lock)


def test_symlink_does_not_substitute_approved_source(bundle, tmp_path):
    root, lock = bundle; path = root / 'core/lib/tools.func'
    original = path.read_bytes(); path.unlink(); target = tmp_path / 'elsewhere'; target.write_bytes(original)
    path.symlink_to(target)
    with pytest.raises(ValueError, match='SOURCE_FILE'): community.verify_sources(root, lock)


def test_group_writable_source_directory_is_not_trusted(bundle):
    root, lock = bundle; (root / 'core/lib').chmod(0o770)
    with pytest.raises(ValueError, match='SOURCE_FILE'): community.verify_sources(root, lock)


@pytest.mark.parametrize('field', ['core_commit', 'scripts_commit'])
def test_mutable_or_different_revision_is_rejected(bundle, field):
    root, lock = bundle; lock[field] = 'main'
    with pytest.raises(ValueError, match='SOURCE_REVISION'): community.verify_sources(root, lock)


def test_hash_manifest_has_no_executable_free_fields(bundle):
    root, lock = bundle; lock['command'] = 'printf untrusted'
    with pytest.raises(ValueError, match='SOURCE_SCHEMA'): community.verify_sources(root, lock)
