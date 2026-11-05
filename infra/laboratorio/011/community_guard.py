#!/usr/bin/env python3
"""Guardas del guest piloto: repositorios congelados y artefacto de release fijado."""

import hashlib
from fnmatch import fnmatchcase
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlsplit


spec = importlib.util.spec_from_file_location('nap_community_sources', Path(__file__).with_name('spike_community.py'))
community = importlib.util.module_from_spec(spec); spec.loader.exec_module(community)
PLAN = Path('/opt/nap-community/community-dependencies.lock.json')
ARTIFACT_DIR = Path('/var/cache/nap-community-011')
ERROR_PATH = Path('/run/nap-community-error.json')
APT_SOURCE_FILE = 'debian.sources'


def record_error(error):
    codes = {'APT_ARGUMENTS', 'APT_SOURCES_CHANGED', 'APT_RELEASE_CHANGED', 'APT_COMMAND_FAILED', 'DEPENDENCY_ARTIFACT'}
    code = str(error) if str(error) in codes else 'INFRASTRUCTURE_NOT_CONFIRMED'
    try:
        fd = os.open(ERROR_PATH, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as target: json.dump({'code': code}, target)
    except OSError:
        pass


def apt_sources(plan):
    community.validate_dependencies(plan)
    sections = []
    for release in plan['apt']['releases']:
        uri = f"https://snapshot.debian.org/archive/{release['archive']}/{release['timestamp']}/"
        sections.append(f"Types: deb\nURIs: {uri}\nSuites: {release['suite']}\nComponents: main\n"
            'Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg\nCheck-Valid-Until: no\n')
    return '\n'.join(sections)


def apt_release_name(release):
    parsed = urlsplit(release['url'])
    return parsed.netloc + parsed.path.replace('/', '_')


def verify_apt_state(root, plan, *, require_releases=True):
    root = Path(root)
    sources = root / 'etc/apt/sources.list.d'
    legacy = root / 'etc/apt/sources.list'
    files = sorted([*sources.glob('*.list'), *sources.glob('*.sources')])
    expected = sources / APT_SOURCE_FILE
    if (legacy.exists() or files != [expected] or expected.is_symlink()
            or expected.read_text() != apt_sources(plan)):
        raise ValueError('APT_SOURCES_CHANGED')
    if not require_releases: return
    for release in plan['apt']['releases']:
        path = root / 'var/lib/apt/lists' / apt_release_name(release)
        if (not path.is_file() or path.is_symlink()
                or hashlib.sha256(path.read_bytes()).hexdigest() != release['sha256']):
            raise ValueError('APT_RELEASE_CHANGED')


def validate_apt_arguments(args, *, approved_artifact=None):
    commands = {'update', 'install', 'upgrade', 'dist-upgrade', 'autoremove', 'remove', 'purge', 'clean', 'autoclean'}
    options = {'-y', '--yes', '--assume-yes', '-qq', '-q', '--quiet', '--no-install-recommends',
               '--fix-broken', '--fix-missing', '--only-upgrade', '--purge', '--autoremove'}
    iterator = iter(args); command = None
    for argument in iterator:
        if argument == '-o':
            if next(iterator, '') not in {'Dpkg::Options::=--force-confold', 'Dpkg::Options::=--force-confdef'}:
                raise ValueError('APT_ARGUMENTS')
        elif argument.startswith('-'):
            if argument not in options: raise ValueError('APT_ARGUMENTS')
        elif command is None:
            if argument not in commands: raise ValueError('APT_ARGUMENTS')
            command = argument
        elif argument.startswith('/'):
            if argument != approved_artifact: raise ValueError('APT_ARGUMENTS')
        elif not re.fullmatch(r'[a-z0-9][a-z0-9+.\-]*(?::(?:amd64|all))?(?:=[A-Za-z0-9.+:~_\-]+)?', argument):
            raise ValueError('APT_ARGUMENTS')
    if command is None: raise ValueError('APT_ARGUMENTS')
    return command


def artifact_path(plan):
    return ARTIFACT_DIR / urlsplit(plan['caddy']['url']).path.rsplit('/', 1)[1]


def validate_release_arguments(args, plan):
    community.validate_dependencies(plan)
    if len(args) != 7: raise ValueError('DEPENDENCY_ARTIFACT')
    application, repository, kind, requested, directory, pattern, frozen_version = args
    parts = urlsplit(plan['caddy']['url']).path.strip('/').split('/')
    expected_repository = '/'.join(parts[:2])
    if (repository != expected_repository or application != parts[1] or kind != 'binary'
            or requested not in {'latest', plan['caddy']['version'], 'v' + plan['caddy']['version']}
            or frozen_version != plan['caddy']['version'] or directory != '/opt/' + application
            or not fnmatchcase(artifact_path(plan).name, pattern)):
        raise ValueError('DEPENDENCY_ARTIFACT')


def verify_artifact(plan):
    path = artifact_path(plan)
    if (not path.is_file() or path.is_symlink() or path.stat().st_size != plan['caddy']['bytes']
            or hashlib.sha256(path.read_bytes()).hexdigest() != plan['caddy']['sha256']):
        raise ValueError('DEPENDENCY_ARTIFACT')
    return path


def guarded_apt(args, plan):
    community.validate_dependencies(plan)
    command = validate_apt_arguments(args, approved_artifact=str(artifact_path(plan)))
    verify_apt_state('/', plan, require_releases=command != 'update')
    if any(v.startswith('/') for v in args): verify_artifact(plan)
    result = subprocess.run(['/usr/bin/apt-get', *args], stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=900)
    if result.returncode: raise ValueError('APT_COMMAND_FAILED')
    verify_apt_state('/', plan)


def main():
    try:
        plan = community.validate_dependencies(json.loads(PLAN.read_text()))
        if len(sys.argv) > 1 and sys.argv[1] == 'apt':
            guarded_apt(sys.argv[2:], plan)
        elif len(sys.argv) == 9 and sys.argv[1] == 'release':
            validate_release_arguments(sys.argv[2:], plan)
            path = verify_artifact(plan)
            guarded_apt(['install', '-y', str(path)], plan)
        else: raise ValueError('APT_ARGUMENTS')
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        record_error(error)
        return 86


if __name__ == '__main__':
    raise SystemExit(main())
