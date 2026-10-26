#!/usr/bin/env python3
"""Bootstrap 011: registry en el controlador y namespace nuevo en el nodo.

No modifica SSH/cuentas/puentes/pools/invitados existentes ni habilita perfiles.
La política de red se deja pendiente: debe imponerse antes de arrancar cada guest.
"""

import argparse
import base64
from copy import deepcopy
import fcntl
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import re
import ssl
import stat
import subprocess
from urllib.error import HTTPError
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler, ProxyHandler


def sibling(name):
    spec = importlib.util.spec_from_file_location('nap011_' + name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


preflight = sibling('preflight')
ENDPOINT = 'https://172.16.36.1:5443'


def validate_config(manifest, config):
    preflight.validate_manifest(manifest)
    if not isinstance(config, dict) or set(config) != {'schema_version', 'registry', 'network'}:
        raise ValueError('INVALID_BOOTSTRAP')
    if config['schema_version'] != 'nap-lab-bootstrap/1':
        raise ValueError('INVALID_BOOTSTRAP')
    registry = config['registry']
    if not isinstance(registry, dict) or set(registry) != {'endpoint', 'ca_pem', 'username', 'password'}:
        raise ValueError('INVALID_REGISTRY')
    if (registry['endpoint'] != ENDPOINT or registry['username'] != 'nap011reader'
            or not isinstance(registry['password'], str) or not 20 <= len(registry['password']) <= 128
            or not re.fullmatch('[A-Za-z0-9_-]+', registry['password'])
            or not isinstance(registry['ca_pem'], str) or not 1 <= len(registry['ca_pem']) <= 16384):
        raise ValueError('INVALID_REGISTRY')
    network = config['network']
    if (not isinstance(network, dict) or set(network) != {'cidr', 'bridge', 'gateway', 'slots'}
            or network['cidr'] != '172.16.36.0/24' or network['bridge'] != manifest['bridge']
            or network['gateway'] != '172.16.36.2' or not isinstance(network['slots'], list)
            or not 1 <= len(network['slots']) <= 8):
        raise ValueError('INVALID_NETWORK')
    seen_ip, seen_mac, seen_host = set(), set(), set()
    allowed = {f'172.16.36.{n}' for n in range(81, 89)}
    for slot in network['slots']:
        if not isinstance(slot, dict) or set(slot) != {'address', 'mac', 'host'}:
            raise ValueError('INVALID_SLOT')
        if (slot['address'] not in allowed or slot['address'] in seen_ip
                or not isinstance(slot['mac'], str) or not re.fullmatch(r'02:11(?::[0-9a-f]{2}){4}', slot['mac'])
                or slot['mac'] in seen_mac or not isinstance(slot['host'], str)
                or not re.fullmatch(r'app[1-8]\.nap011\.test', slot['host']) or slot['host'] in seen_host):
            raise ValueError('INVALID_SLOT')
        ipaddress.IPv4Address(slot['address'])
        seen_ip.add(slot['address']); seen_mac.add(slot['mac']); seen_host.add(slot['host'])
    return config


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def verify_registry(config):
    registry = config['registry']
    context = ssl.create_default_context(cadata=registry['ca_pem'])
    opener = build_opener(ProxyHandler({}), HTTPSHandler(context=context), NoRedirect())
    auth = 'Basic ' + base64.b64encode((registry['username'] + ':' + registry['password']).encode()).decode()
    request = Request(ENDPOINT + '/v2/', headers={'Authorization': auth})
    try:
        with opener.open(request, timeout=5) as response:
            return response.status == 200
    except (OSError, HTTPError):
        return False


def safe_directory(path):
    if path.exists() or path.is_symlink():
        info = path.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o022):
            raise ValueError('UNTRUSTED_DIRECTORY')
    else:
        path.mkdir(mode=0o700)


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()


def prepare_node(manifest, config, *, apply=False, root=Path('/'),
                 inventory_provider=None, registry_verifier=None):
    validate_config(manifest, config)
    inventory = (inventory_provider or preflight.collect_node)(manifest)
    report = preflight.evaluate(manifest, inventory)
    if not report['node_prerequisites_ok']:
        raise ValueError('NODE_PREREQUISITES_NOT_CONFIRMED')
    candidates = deepcopy(manifest)
    for profile in candidates['profiles']:
        profile['base_sha256'] = inventory['templates'][profile['base']]
    network = {**config['network'], 'state': 'pendiente_validacion',
               'policy': {'deny_management': True, 'deny_other_catedras': True,
                          'enforce_before_guest_start': True}}
    stable_inventory = {key: inventory[key] for key in ('schema_version', 'read_only', 'node',
                        'tools', 'apparmor_enabled', 'templates')}
    files = {'candidatos.json': encode(candidates), 'network.json': encode(network),
             'registry.json': encode({'endpoint': ENDPOINT, 'ca_file': 'ca.crt', 'state': 'pendiente_validacion'}),
             'ca.crt': config['registry']['ca_pem'].encode(), 'inventory.json': encode(stable_inventory)}
    public = {'scope': 'laboratorio_local', 'profiles_enabled': [],
              'network_policy_staged': True, 'guest_network_enforced': False,
              'templates': inventory['templates'], 'next': 'SPIKES_REQUIRED'}
    if not apply:
        return {**public, 'state': 'plan_without_changes'}
    root = Path(root)
    if root == Path('/') and os.geteuid() != 0:
        raise ValueError('ROOT_REQUIRED_ON_NODE')
    if not (registry_verifier or verify_registry)(config):
        raise ValueError('REGISTRY_NOT_CONFIRMED')
    destination = root / 'etc/nap/applications-011'
    for folder in (root, root / 'etc', root / 'etc/nap', destination):
        safe_directory(folder)
    lock = os.open(destination / '.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(lock)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise ValueError('UNTRUSTED_LOCK')
        fcntl.flock(lock, fcntl.LOCK_EX)
        pending = []
        for name, content in files.items():
            path = destination / name
            if path.exists() or path.is_symlink():
                info = path.lstat()
                if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid()
                        or info.st_mode & 0o077 or path.read_bytes() != content):
                    raise ValueError('EXISTING_FILE_DIFFERS')
            else:
                pending.append((path, content))
        created = []
        try:
            for path, content in pending:
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                info = os.fstat(fd)
                created.append((path, info.st_ino))
                with os.fdopen(fd, 'wb') as target:
                    target.write(content); target.flush(); os.fsync(target.fileno())
        except BaseException:
            for path, inode in reversed(created):
                if path.exists() and not path.is_symlink() and path.lstat().st_ino == inode:
                    path.unlink()
            raise
        return {**public, 'state': 'node_bootstrap_staged' if pending else 'node_bootstrap_already_staged'}
    finally:
        os.close(lock)


def controller_config(registry_root):
    accounts = preflight.read_json(registry_root / 'accounts.json')
    return {'schema_version': 'nap-lab-bootstrap/1', 'registry': {
        'endpoint': ENDPOINT, 'ca_pem': (registry_root / 'pki/ca.crt').read_text(),
        'username': 'nap011reader', 'password': accounts['nap011reader']},
        'network': {'cidr': '172.16.36.0/24', 'bridge': 'vmbr0', 'gateway': '172.16.36.2',
                    'slots': [{'address': f'172.16.36.{80+n}', 'mac': f'02:11:00:00:00:{80+n:02x}',
                               'host': f'app{n}.nap011.test'} for n in range(1, 9)]}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--controller', action='store_true')
    parser.add_argument('--private-dir', type=Path, default=Path.home() / '.local/share/nap011/registry')
    parser.add_argument('--manifest', type=Path, default=Path(__file__).with_name('candidatos.json'))
    parser.add_argument('--config', type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    try:
        if args.controller:
            registry = sibling('registry_lab')
            parent = args.private_dir.parent
            if args.apply:
                if not parent.exists():
                    parent.mkdir(mode=0o700, parents=True)
                if parent.is_symlink() or parent.stat().st_uid != os.geteuid() or parent.stat().st_mode & 0o077:
                    raise ValueError('UNTRUSTED_DIRECTORY')
            result = registry.prepare(args.private_dir, apply=args.apply)
            if args.apply:
                config_path = args.private_dir.parent / 'bootstrap-node.json'
                value = controller_config(args.private_dir)
                validate_config(preflight.read_json(args.manifest), value)
                if config_path.exists():
                    if preflight.read_json(config_path) != value:
                        raise ValueError('EXISTING_FILE_DIFFERS')
                else:
                    registry.private_write(config_path, encode(value))
        else:
            if args.config is None:
                raise ValueError('PRIVATE_CONFIG_REQUIRED')
            result = prepare_node(preflight.read_json(args.manifest), preflight.read_json(args.config), apply=args.apply)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        codes = {'INVALID_BOOTSTRAP', 'INVALID_REGISTRY', 'INVALID_NETWORK', 'INVALID_SLOT',
                 'UNTRUSTED_DIRECTORY', 'NODE_PREREQUISITES_NOT_CONFIRMED', 'ROOT_REQUIRED_ON_NODE',
                 'REGISTRY_NOT_CONFIRMED', 'UNTRUSTED_LOCK', 'EXISTING_FILE_DIFFERS', 'PRIVATE_CONFIG_REQUIRED',
                 'REGISTRY_NAME_OCCUPIED', 'REGISTRY_PRIVATE_STATE_MISSING', 'UNTRUSTED_PRIVATE_DIRECTORY',
                 'REGISTRY_ISOLATION_NOT_CONFIRMED',
                 'REGISTRY_TLS_AUTH_NOT_CONFIRMED', 'REGISTRY_READ_ONLY_NOT_CONFIRMED', 'REGISTRY_IMAGE_NOT_CONFIRMED'}
        print(json.dumps({'state': 'bootstrap_not_confirmed', 'profiles_enabled': [],
                          'code': str(error) if str(error) in codes else 'BOOTSTRAP_IO_NOT_CONFIRMED',
                          'next': 'Conservar archivos privados y revisar el diagnóstico; no repetir a ciegas'}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
