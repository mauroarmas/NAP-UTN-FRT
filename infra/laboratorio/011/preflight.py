#!/usr/bin/env python3
"""Inventario de sólo lectura. Ningún resultado habilita perfiles ni modifica el nodo.

--node recoge hechos del nodo; --diagnostic evalúa un inventario previamente guardado.
Los datos privados de entrada no se copian al reporte. Sin inventario, indica pendientes.
"""

import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess


SIZES = {'small': {'vcpus': 1, 'ram_mb': 512, 'disk_gb': 4},
         'medium': {'vcpus': 2, 'ram_mb': 1024, 'disk_gb': 8}}
PROFILE_IDS = {'docker-ubuntu24', 'community-mariadb', 'community-caddy'}
ROOT_KEYS = {'schema_version', 'environment', 'node', 'host', 'bridge', 'sizes',
             'max_active_jobs', 'profiles'}
TEMPLATE_ROOT = Path('/var/lib/vz/template/cache')
TOOLS = {'python3': 'python3', 'pct': 'pct', 'systemd': 'systemctl', 'nft': 'nft'}
SYSTEM_PATH = '/usr/sbin:/usr/bin:/sbin:/bin'


def read_json(path):
    """Lectura acotada sin enlaces; los archivos privados siguen siendo privados."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 1048576 or info.st_mode & 0o022:
            raise ValueError('UNTRUSTED_INPUT')
        with os.fdopen(fd, 'rb', closefd=False) as source:
            data = source.read(1048577)
        if len(data) > 1048576:
            raise ValueError('INPUT_TOO_LARGE')
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError('DUPLICATE_KEY')
                result[key] = value
            return result
        return json.loads(data, object_pairs_hook=unique)
    finally:
        os.close(fd)


def validate_manifest(value):
    if (not isinstance(value, dict) or set(value) != ROOT_KEYS
            or value['schema_version'] != 'nap-application-candidates/1'
            or value['environment'] != 'laboratorio_local' or value['sizes'] != SIZES
            or type(value['max_active_jobs']) is not int or value['max_active_jobs'] != 2):
        raise ValueError('INVALID_CANDIDATES')
    if not isinstance(value['node'], str) or not re.fullmatch(r'[a-zA-Z0-9-]{1,63}', value['node']):
        raise ValueError('INVALID_NODE')
    host = ipaddress.ip_address(value['host'])
    if host.version != 4 or not host.is_private or host.is_loopback or host.is_link_local:
        raise ValueError('INVALID_LAB_HOST')
    if not re.fullmatch(r'vmbr[0-9]{1,3}', value['bridge']):
        raise ValueError('INVALID_BRIDGE')
    profiles = value['profiles']
    if not isinstance(profiles, list) or len(profiles) != 3:
        raise ValueError('INVALID_PROFILES')
    ids = set()
    for profile in profiles:
        common = {'id', 'state', 'base', 'base_sha256', 'initial_size'}
        if not isinstance(profile, dict) or not common <= profile.keys():
            raise ValueError('INVALID_PROFILE')
        if profile['id'] not in PROFILE_IDS or profile['id'] in ids:
            raise ValueError('INVALID_PROFILE')
        ids.add(profile['id'])
        if profile['state'] != 'pendiente_validacion' or profile['initial_size'] != 'medium':
            raise ValueError('UNCERTIFIED_PROFILE')
        expected_os = 'ubuntu-24.04' if profile['id'] == 'docker-ubuntu24' else 'debian-13'
        if (not isinstance(profile['base'], str) or
                not re.fullmatch(re.escape(expected_os) + r'-standard_[0-9A-Za-z.+-]+_amd64\.tar\.zst', profile['base'])):
            raise ValueError('INVALID_BASE')
        digest = profile['base_sha256']
        if digest is not None and (not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest)):
            raise ValueError('INVALID_HASH')
        if profile['id'] == 'docker-ubuntu24':
            if set(profile) != common | {'features'} or profile['features'] != ['nesting=1', 'keyctl=1']:
                raise ValueError('INVALID_FEATURES')
        else:
            if set(profile) != common | {'source_commit', 'core_commit', 'answers'}:
                raise ValueError('INVALID_PROFILE')
            for key in ('source_commit', 'core_commit'):
                if not isinstance(profile[key], str) or not re.fullmatch('[0-9a-f]{40}', profile[key]):
                    raise ValueError('INVALID_SOURCE')
            answer = ('var_mariadb_phpmyadmin' if profile['id'] == 'community-mariadb'
                      else 'var_caddy_xcaddy')
            if profile['answers'] != {answer: 'no'}:
                raise ValueError('INVALID_ANSWERS')
    return value


def file_sha256(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o022 or not 0 < info.st_size <= 2 * 1024**3:
            raise ValueError('UNTRUSTED_BASE')
        digest = hashlib.sha256()
        with os.fdopen(fd, 'rb', closefd=False) as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b''):
                digest.update(chunk)
        return digest.hexdigest()
    finally:
        os.close(fd)


def collect_node(manifest):
    """Sólo stat/hash y aa-enabled: no shells, descargas o cambios de configuración."""
    validate_manifest(manifest)
    aa = shutil.which('aa-enabled', path=SYSTEM_PATH)
    apparmor = None
    if aa:
        try:
            apparmor = subprocess.run([aa, '--quiet'], stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5,
                env={'PATH': SYSTEM_PATH, 'LC_ALL': 'C'}, check=False).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            pass
    templates = {}
    for name in {p['base'] for p in manifest['profiles']}:
        try:
            templates[name] = file_sha256(TEMPLATE_ROOT / name)
        except (OSError, ValueError):
            templates[name] = None
    return {'schema_version': 'nap-node-preflight/1', 'read_only': True,
            'node': os.uname().nodename.split('.')[0],
            'tools': {key: shutil.which(binary, path=SYSTEM_PATH) is not None for key, binary in TOOLS.items()},
            'apparmor_enabled': apparmor,
            'available_bytes': shutil.disk_usage('/var/lib/vz' if Path('/var/lib/vz').exists() else '/').free,
            'templates': templates}


def evaluate(manifest, inventory):
    validate_manifest(manifest)
    inventory = inventory if isinstance(inventory, dict) else {}
    blockers = []
    valid = (inventory.get('schema_version') == 'nap-node-preflight/1'
             and inventory.get('read_only') is True and inventory.get('node') == manifest['node'])
    if not valid:
        blockers.append('NODE_INVENTORY_REQUIRED')
        inventory = {}
    tools = inventory.get('tools', {})
    if not isinstance(tools, dict) or any(tools.get(k) is not True for k in TOOLS):
        blockers.append('NODE_TOOLS_NOT_CONFIRMED')
    if inventory.get('apparmor_enabled') is not True:
        blockers.append('APPARMOR_NOT_CONFIRMED')
    free = inventory.get('available_bytes')
    if type(free) is not int or free < 20 * 1024**3:
        blockers.append('FREE_SPACE_NOT_CONFIRMED')
    templates = inventory.get('templates', {})
    if not isinstance(templates, dict):
        templates = {}
    profiles = []
    for candidate in manifest['profiles']:
        observed = templates.get(candidate['base'])
        if not isinstance(observed, str) or not re.fullmatch('[0-9a-f]{64}', observed):
            observed = None
            blockers.append('BASE_HASH_NOT_CONFIRMED')
        elif candidate['base_sha256'] is not None and observed != candidate['base_sha256']:
            blockers.append('BASE_HASH_MISMATCH')
        profiles.append({'id': candidate['id'], 'state': 'pendiente_validacion',
                         'base': candidate['base'], 'observed_base_sha256': observed})
    node_ready = not blockers
    # Disponer de binarios y hashes no demuestra compatibilidad operativa ni aislamiento.
    blockers.extend(['BOOTSTRAP_REVIEW_REQUIRED', 'REAL_GATES_REQUIRED'])
    return {'schema_version': 'nap-preflight-result/1', 'read_only': True,
            'environment': manifest['environment'], 'scope': 'node_prerequisites_only',
            'node_prerequisites_ok': node_ready, 'ready_for_spikes': False,
            'profiles_enabled': [], 'profiles': profiles, 'blockers': sorted(set(blockers))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=Path(__file__).with_name('candidatos.json'))
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--node', action='store_true', help='Recoger inventario local de sólo lectura')
    group.add_argument('--diagnostic', type=Path, help='Evaluar inventario guardado, sin copiar campos privados')
    args = parser.parse_args()
    try:
        manifest = validate_manifest(read_json(args.manifest))
        if args.node:
            result = collect_node(manifest)
        else:
            result = evaluate(manifest, read_json(args.diagnostic) if args.diagnostic else {})
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError):
        print(json.dumps({'error': 'PREFLIGHT_INPUT_INVALID', 'read_only': True}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
