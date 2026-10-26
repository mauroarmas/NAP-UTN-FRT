#!/usr/bin/env python3
"""Preparación de fuentes cerradas del gate Community; no habilita perfiles.

La verificación de fuentes es de sólo lectura. No ejecuta wrappers del nodo ni
descarga helpers ausentes. La aceptación requiere además el ensayo real guest.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import base64
import fcntl
import importlib.util
import subprocess
import shlex
from datetime import datetime


CORE_COMMIT = '81a2e2ae7d42dea39fd5dd7903b266b5e607c811'
SCRIPTS_COMMIT = '5d477b0b6efb4141da0b90cadcec32f8641a815c'
CORE_FILES = ('lxc/install.func', 'core/core.func', 'core/error_handler.func',
              'lib/tools.func', 'lib/alpine.func', 'lib/system.func', 'lib/forge.func',
              'lib/runtime.func', 'lib/db.func', 'lib/hwaccel.func', 'LICENSE')
SOURCE_FILES = tuple('core/' + name for name in CORE_FILES) + (
    'proxmox/install/mariadb-install.sh', 'proxmox/install/caddy-install.sh', 'proxmox/LICENSE')


def validate_dependencies(lock):
    """Sólo coordenadas inmutables de los dos pilotos; ninguna URL u orden libre."""
    if (not isinstance(lock, dict) or set(lock) != {'schema_version', 'scope', 'apt', 'caddy'}
            or lock['schema_version'] != 'nap-community-dependencies/1' or lock['scope'] != 'laboratorio_local'):
        raise ValueError('DEPENDENCY_SCHEMA')
    apt = lock['apt']
    if (not isinstance(apt, dict) or set(apt) != {'releases', 'verified_keyring_version'}
            or not isinstance(apt['releases'], list) or len(apt['releases']) != 3
            or not isinstance(apt['verified_keyring_version'], str)):
        raise ValueError('DEPENDENCY_REPOSITORY')
    pairs, timestamps = set(), set()
    allowed = {('debian', 'trixie'), ('debian', 'trixie-updates'), ('debian-security', 'trixie-security')}
    for release in apt['releases']:
        if not isinstance(release, dict) or set(release) != {'archive', 'suite', 'timestamp', 'url', 'sha256'}:
            raise ValueError('DEPENDENCY_REPOSITORY')
        if not all(isinstance(v, str) for v in release.values()): raise ValueError('DEPENDENCY_REPOSITORY')
        pair = (release['archive'], release['suite'])
        if pair not in allowed or pair in pairs: raise ValueError('DEPENDENCY_REPOSITORY')
        try: datetime.strptime(release['timestamp'], '%Y%m%dT%H%M%SZ')
        except ValueError: raise ValueError('DEPENDENCY_REPOSITORY') from None
        expected = (f"https://snapshot.debian.org/archive/{release['archive']}/{release['timestamp']}/"
                    f"dists/{release['suite']}/InRelease")
        if release['url'] != expected or not re.fullmatch('[0-9a-f]{64}', release['sha256']):
            raise ValueError('DEPENDENCY_REPOSITORY')
        pairs.add(pair); timestamps.add(release['timestamp'])
    if pairs != allowed or len(timestamps) != 1: raise ValueError('DEPENDENCY_REPOSITORY')
    artifact = lock['caddy']
    if (not isinstance(artifact, dict) or set(artifact) != {'version', 'url', 'sha256', 'bytes', 'published_at'}
            or not isinstance(artifact['version'], str) or not re.fullmatch(r'\d+\.\d+\.\d+', artifact['version'])
            or not isinstance(artifact['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', artifact['sha256'])
            or type(artifact['bytes']) is not int or not 0 < artifact['bytes'] <= 33554432):
        raise ValueError('DEPENDENCY_ARTIFACT')
    expected = (f"https://github.com/caddyserver/caddy/releases/download/v{artifact['version']}/"
                f"caddy_{artifact['version']}_linux_amd64.deb")
    if artifact['url'] != expected or not isinstance(artifact['published_at'], str):
        raise ValueError('DEPENDENCY_ARTIFACT')
    try: datetime.fromisoformat(artifact['published_at'].replace('Z', '+00:00'))
    except ValueError: raise ValueError('DEPENDENCY_ARTIFACT') from None
    return lock


def verify_sources(root, lock):
    """El contenido aprobado se entrega al empaquetador; nunca se hace source aquí."""
    if (not isinstance(lock, dict) or set(lock) != {'schema_version', 'core_commit', 'scripts_commit', 'sources'}
            or lock.get('schema_version') != 'nap-community-sources/1'):
        raise ValueError('SOURCE_SCHEMA')
    if lock['core_commit'] != CORE_COMMIT or lock['scripts_commit'] != SCRIPTS_COMMIT:
        raise ValueError('SOURCE_REVISION')
    if not isinstance(lock['sources'], dict) or set(lock['sources']) != set(SOURCE_FILES):
        raise ValueError('SOURCE_CLOSURE')
    root = Path(root)
    result = {}
    for name, digest in lock['sources'].items():
        if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
            raise ValueError('SOURCE_HASH')
        try:
            path = root / name
            for directory in [root, *reversed(list(path.parents)[:len(Path(name).parts) - 1])]:
                info = directory.lstat()
                if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o022:
                    raise ValueError('SOURCE_FILE')
            info = path.lstat()
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_nlink != 1
                    or info.st_mode & 0o022 or not 0 < info.st_size <= 2097152):
                raise ValueError('SOURCE_FILE')
            content = path.read_bytes()
        except FileNotFoundError:
            raise ValueError('SOURCE_MISSING') from None
        if hashlib.sha256(content).hexdigest() != digest:
            raise ValueError('SOURCE_HASH')
        result[name] = content
    return result


def sibling(name):
    spec = importlib.util.spec_from_file_location('community_lab_' + name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def make_node(bootstrap, manifest, config, marker, application, source_root, source_lock, dependencies):
    """Adaptador del gate: reutiliza identidad, aislamiento y limpieza de T005."""
    common = sibling('spike_docker')
    guard = sibling('community_guard')
    sources = verify_sources(source_root, source_lock)
    validate_dependencies(dependencies)
    application_profile = 'community-' + application
    if application not in {'mariadb', 'caddy'}: raise ValueError('INVALID_APPLICATION')
    own_names = ['spike_community.py', 'community_guard.py', 'community_harness.sh',
                 'community_bootstrap_policy.func', 'community_install_policy.func',
                 'community-sources.lock.json', 'community-dependencies.lock.json']
    own = {name: Path(__file__).with_name(name).read_bytes() for name in own_names}
    if json.loads(own['community-sources.lock.json']) != source_lock:
        raise ValueError('SOURCE_REQUEST_CHANGED')
    if json.loads(own['community-dependencies.lock.json']) != dependencies:
        raise ValueError('DEPENDENCY_REQUEST_CHANGED')
    files = {**own, **{'sources/' + name: content for name, content in sources.items()}}
    payload = json.dumps({'application': application,
        'files': {name: base64.b64encode(data).decode() for name, data in files.items()}}, sort_keys=True).encode()
    if len(payload) > 2097152: raise ValueError('PAYLOAD_LIMIT')
    asset = Path(source_root) / guard.artifact_path(dependencies).name
    if application == 'caddy':
        info = asset.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_mode & 0o022 or info.st_uid != os.geteuid()
                or info.st_size != dependencies['caddy']['bytes']
                or hashlib.sha256(asset.read_bytes()).hexdigest() != dependencies['caddy']['sha256']):
            raise ValueError('DEPENDENCY_ARTIFACT')

    class CommunityNode(common.Node):
        def __init__(self):
            super().__init__(bootstrap, manifest, config, marker, profile_id=application_profile,
                             program_path=Path(__file__).with_name('guest_community_probe.py'))
            self.fingerprint = hashlib.sha256(self.fingerprint.encode() + payload
                + Path(__file__).read_bytes() + Path(__file__).with_name('community_guard.py').read_bytes()).hexdigest()

        def guest(self, args, **kwargs):
            self.owned(marker)
            return common.command(['/usr/sbin/pct', 'exec', str(common.VMID), '--', *args], **kwargs)

        def probe(self, marker):
            self.check_confinement(marker)
            self.guest(['passwd', '-l', 'root'])
            # Sólo se modifica el rootfs recién creado, después de comprobar propiedad.
            # Se retiran fuentes/listas anteriores antes de la primera consulta APT.
            setup = '''umask 022
mkdir -p /etc/apt/sources.list.d
rm -f /etc/apt/sources.list
find /etc/apt/sources.list.d -maxdepth 1 -type f \\( -name '*.list' -o -name '*.sources' \\) -delete
rm -rf /var/lib/apt/lists/*
cat > /etc/apt/sources.list.d/debian.sources
'''
            self.guest(['/bin/sh', '-c', setup], data=guard.apt_sources(dependencies).encode())
            self.guest(['env', '-i', 'PATH=/usr/sbin:/usr/bin:/sbin:/bin', 'DEBIAN_FRONTEND=noninteractive',
                        '/usr/bin/apt-get', 'update', '-qq'], timeout=600)
            raw = self.guest(['/usr/bin/find', '/var/lib/apt/lists', '-maxdepth', '1', '-type', 'f', '-name',
                '*InRelease', '-exec', '/usr/bin/sha256sum', '{}', '+'], capture=True).decode()
            observed = {Path(line.split(None, 1)[1].strip()).name: line.split()[0] for line in raw.splitlines()}
            expected = {guard.apt_release_name(release): release['sha256'] for release in dependencies['apt']['releases']}
            if observed != expected: raise ValueError('COMMUNITY_APT_RELEASE_CHANGED')
            self.guest(['env', '-i', 'PATH=/usr/sbin:/usr/bin:/sbin:/bin', 'DEBIAN_FRONTEND=noninteractive',
                '/usr/bin/apt-get', '-y', '--no-install-recommends', 'install', 'python3', 'curl', 'iproute2'], timeout=600)
            if application == 'caddy':
                # Binario público cerrado por SHA. No se ejecuta en el nodo.
                destination = str(guard.artifact_path(dependencies))
                command = 'umask 022; mkdir -p /var/cache/nap-community-011; cat > ' + shlex.quote(destination)
                self.guest(['/bin/sh', '-c', command], data=asset.read_bytes(), timeout=120)
            raw = self.guest(['env', '-i', 'PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
                '/usr/bin/python3', '-I', '-c', self.program.decode()], data=payload, capture=True, timeout=1300)
            data = json.loads(raw)
            if data.get('state') != 'guest_probe_passed':
                self.failed_guest_phase = data.get('phase')
                codes = {'SOURCE_REJECTED', 'UNDECLARED_HELPER', 'UNDECLARED_DOWNLOAD', 'UNRESOLVED_PROMPT',
                    'INSTALLER_FAILED', 'PRODUCT_PROBE_FAILED', 'MEDIUM_NOT_CONFIRMED', 'LOGIN_OR_LOG_POLICY',
                    'APT_SOURCES_CHANGED', 'APT_RELEASE_CHANGED'}
                code = data.get('code') if data.get('code') in codes else 'INFRASTRUCTURE_NOT_CONFIRMED'
                raise ValueError('COMMUNITY_' + code)
            data['external_firewall_counters'] = self.firewall_counters()
            data['confinement'] = self.confinement_observations
            return data

    return CommunityNode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources', type=Path, required=True)
    parser.add_argument('--lock', type=Path, required=True)
    parser.add_argument('--dependencies', type=Path, default=Path(__file__).with_name('community-dependencies.lock.json'))
    parser.add_argument('--manifest', type=Path, default=Path(__file__).with_name('candidatos.json'))
    parser.add_argument('--config', type=Path)
    parser.add_argument('--application', choices=['mariadb', 'caddy'])
    parser.add_argument('--run-id')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--cleanup-only', action='store_true')
    parser.add_argument('--accepted-prior-fingerprint')
    args = parser.parse_args()
    try:
        # El lock versionado no contiene secretos ni órdenes de ejecución.
        if args.lock.stat().st_size > 1048576: raise ValueError('SOURCE_SCHEMA')
        source_lock = json.loads(args.lock.read_text())
        content = verify_sources(args.sources, source_lock)
        if args.apply:
            if os.geteuid() != 0: raise ValueError('ROOT_REQUIRED')
            if args.config is None or args.application is None or args.run_id is None: raise ValueError('PROBE_CONFIG_REQUIRED')
            common = sibling('spike_docker'); bootstrap = sibling('preparar_entorno')
            marker = {'purpose': common.COMMUNITY_PURPOSE, 'run_id': args.run_id}; common.validate_marker(marker)
            node = make_node(bootstrap, bootstrap.preflight.read_json(args.manifest),
                bootstrap.preflight.read_json(args.config), marker, args.application, args.sources, source_lock,
                validate_dependencies(json.loads(args.dependencies.read_text())))
            directory = Path('/var/lib/nap-lab011'); bootstrap.safe_directory(directory)
            lock = os.open(directory / '.docker-spike.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            try:
                info = os.fstat(lock)
                if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_nlink != 1 or info.st_mode & 0o077:
                    raise ValueError('UNTRUSTED_PROBE_LOCK')
                fcntl.flock(lock, fcntl.LOCK_EX)
                journal = directory / (args.run_id + '.json')
                if args.cleanup_only:
                    result = common.reconcile_probe(node, marker, journal,
                        accepted_prior_fingerprint=args.accepted_prior_fingerprint)
                else:
                    if args.accepted_prior_fingerprint: raise ValueError('INVALID_PRIOR_FINGERPRINT')
                    result = common.execute_probe(node, marker, journal)
            finally: os.close(lock)
            if result['state'] not in {'probe_passed', 'probe_cleaned'}:
                print(json.dumps(result)); return 2
        else:
            if args.cleanup_only or args.accepted_prior_fingerprint: raise ValueError('APPLY_REQUIRED')
            result = {'state': 'source_bundle_verified', 'source_count': len(content),
                      'profiles_enabled': [], 'real_guest_gate_pending': True}
        status = 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        codes = {'SOURCE_SCHEMA', 'SOURCE_CLOSURE', 'SOURCE_REVISION', 'SOURCE_FILE', 'SOURCE_MISSING', 'SOURCE_HASH',
                 'SOURCE_REQUEST_CHANGED', 'DEPENDENCY_REQUEST_CHANGED', 'DEPENDENCY_SCHEMA', 'DEPENDENCY_REPOSITORY',
                 'DEPENDENCY_ARTIFACT', 'ROOT_REQUIRED', 'PROBE_CONFIG_REQUIRED', 'UNTRUSTED_PROBE_LOCK',
                 'INVALID_APPLICATION', 'INVALID_PROBE_ORIGIN', 'PROBE_REQUEST_CHANGED', 'PROBE_RECONCILIATION_REQUIRED',
                 'INVALID_PRIOR_FINGERPRINT', 'UNTRUSTED_PROBE_STATE', 'APPLY_REQUIRED', 'INVALID_BOOTSTRAP',
                 'INVALID_NETWORK', 'INVALID_SLOT'}
        code = str(error) if str(error) in codes else 'SOURCE_NOT_CONFIRMED'
        result = {'state': 'source_bundle_rejected', 'code': code, 'profiles_enabled': []}; status = 2
    print(json.dumps(result))
    return status


if __name__ == '__main__':
    raise SystemExit(main())
