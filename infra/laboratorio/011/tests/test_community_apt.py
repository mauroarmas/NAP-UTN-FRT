import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
s = importlib.util.spec_from_file_location('community_apt011', ROOT / 'community_guard.py')
guard = importlib.util.module_from_spec(s); s.loader.exec_module(guard)


@pytest.fixture
def state(tmp_path):
    plan = json.loads((ROOT / 'community-dependencies.lock.json').read_text())
    directory = tmp_path / 'etc/apt/sources.list.d'; directory.mkdir(parents=True)
    (directory / guard.APT_SOURCE_FILE).write_text(guard.apt_sources(plan))
    lists = tmp_path / 'var/lib/apt/lists'; lists.mkdir(parents=True)
    for i, release in enumerate(plan['apt']['releases']):
        content = ('signed release fixture ' + str(i)).encode()
        import hashlib
        release['sha256'] = hashlib.sha256(content).hexdigest()
        (lists / guard.apt_release_name(release)).write_bytes(content)
    return tmp_path, plan


def test_only_the_frozen_sources_and_release_hashes_are_accepted(state):
    root, plan = state
    guard.verify_apt_state(root, plan)
    extra = root / 'etc/apt/sources.list.d/mutable.list'
    extra.write_text('deb https://deb.debian.org/debian trixie main\n')
    with pytest.raises(ValueError, match='APT_SOURCES_CHANGED'): guard.verify_apt_state(root, plan)


def test_metadata_changed_after_successful_update_cannot_be_installed(state):
    root, plan = state
    (root / 'var/lib/apt/lists' / guard.apt_release_name(plan['apt']['releases'][0])).write_text('changed')
    with pytest.raises(ValueError, match='APT_RELEASE_CHANGED'): guard.verify_apt_state(root, plan)


@pytest.mark.parametrize('args', [['-o', 'Dir::Etc::sourcelist=/tmp/free', 'install', 'mariadb-server'],
    ['--allow-unauthenticated', 'install', 'mariadb-server'], ['-c', '/tmp/config', 'update'],
    ['install', 'https://localhost/other.deb'], ['install', '/tmp/other.deb']])
def test_unapproved_apt_options_or_artifacts_are_rejected(args):
    with pytest.raises(ValueError, match='APT_ARGUMENTS'):
        guard.validate_apt_arguments(args)


def test_upstream_upgrade_and_install_arguments_remain_supported():
    assert guard.validate_apt_arguments(['-o', 'Dpkg::Options::=--force-confold', '-y', 'dist-upgrade']) == 'dist-upgrade'
    assert guard.validate_apt_arguments(['install', '-y', 'mariadb-server', 'mariadb-client']) == 'install'
    assert guard.validate_apt_arguments(['install', '-y', '-o', 'Dpkg::Options::=--force-confdef',
        '-o', 'Dpkg::Options::=--force-confold', 'mariadb-server', 'mariadb-client']) == 'install'


def test_release_helper_cannot_select_another_repository_version_or_architecture():
    plan = json.loads((ROOT / 'community-dependencies.lock.json').read_text())
    version = plan['caddy']['version']
    args = ['caddy', 'caddyserver/caddy', 'binary', 'latest', '/opt/caddy', 'caddy_*_linux_amd64.deb', version]
    guard.validate_release_arguments(args, plan)
    for index, value in [(1, 'other/repository'), (3, '1.0.0'), (4, '/etc'),
                         (5, 'caddy_*_linux_arm64.deb'), (6, 'latest')]:
        changed = list(args); changed[index] = value
        with pytest.raises(ValueError, match='DEPENDENCY_ARTIFACT'):
            guard.validate_release_arguments(changed, plan)


def test_guard_error_receipt_has_only_closed_code_and_never_overwrites_files(tmp_path, monkeypatch):
    target = tmp_path / 'error.json'; monkeypatch.setattr(guard, 'ERROR_PATH', target)
    guard.record_error(ValueError('password=do-not-copy-secret'))
    assert json.loads(target.read_text()) == {'code': 'INFRASTRUCTURE_NOT_CONFIRMED'}
    assert target.stat().st_mode & 0o077 == 0
    target.unlink(); existing = tmp_path / 'existing'; existing.write_text('keep')
    target.symlink_to(existing)
    guard.record_error(ValueError('APT_RELEASE_CHANGED'))
    assert existing.read_text() == 'keep'
