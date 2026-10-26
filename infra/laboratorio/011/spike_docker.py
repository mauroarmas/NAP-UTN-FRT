#!/usr/bin/env python3
"""Gate técnico Docker/LXC. Un invitado de ensayo; nunca publica una oferta.

VMID reservado de laboratorio. Identidad antes del efecto, firewall por veth antes
de arrancar y limpieza sólo de lo propio con ausencia de CT y volúmenes comprobada.
No instala Docker en Proxmox ni cambia la política general del firewall.
"""

import argparse
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import struct
import subprocess
import sys
import time
from stat import S_ISDIR, S_ISREG
from uuid import UUID


VMID = 900011
NODE = 'proxmox'
PURPOSE = 'nap011-docker-spike'
GI_B = 1024**3


def validate_marker(marker):
    if not isinstance(marker, dict) or set(marker) != {'purpose', 'run_id'} or marker['purpose'] != PURPOSE:
        raise ValueError('INVALID_PROBE_IDENTITY')
    if str(UUID(marker['run_id'])) != marker['run_id']:
        raise ValueError('INVALID_PROBE_IDENTITY')


def firewall_policy(marker, address, mac):
    validate_marker(marker)
    if address != '172.16.36.81' or not re.fullmatch(r'02:11(?::[0-9a-f]{2}){4}', mac):
        raise ValueError('INVALID_PROBE_NETWORK')
    table = 'nap011_' + UUID(marker['run_id']).hex
    veth = f'veth{VMID}i0'
    return f'''table bridge {table} {{
 comment "{marker['run_id']}"
 chain outgoing {{
  ether saddr != {mac} drop
  ether type arp arp saddr ip {address} accept
  ether type arp arp saddr ip 0.0.0.0 arp daddr ip {address} accept
  ether type arp drop
  ether type ip ip saddr != {address} drop
  ct state invalid drop
  ct state established,related accept
  ether type ip ip daddr 172.16.36.1 tcp dport 5443 accept
  ether type ip ip daddr 172.16.36.2 udp dport 53 accept
  ether type ip ip daddr 172.16.36.2 tcp dport 53 accept
  ether type ip ip daddr 172.16.36.100 counter drop comment "nap011_node_block"
  ether type ip ip daddr 172.16.36.63 counter drop comment "nap011_peer_block"
  ether type ip ip daddr {{ 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 127.0.0.0/8, 169.254.0.0/16 }} drop
  ether type ip tcp dport {{ 80, 443 }} accept
  drop
 }}
 chain incoming {{
  ether type arp accept
  ct state invalid drop
  ct state established,related accept
  ether type ip ip saddr 172.16.36.1 ip daddr {address} tcp dport 8080 accept
  drop
 }}
 chain forwarded {{
  type filter hook forward priority -300; policy accept;
  iifname "{veth}" jump outgoing
  oifname "{veth}" jump incoming
 }}
 chain to_host {{
  type filter hook input priority -300; policy accept;
  iifname "{veth}" jump outgoing
 }}
 chain from_host {{
  type filter hook output priority -300; policy accept;
  oifname "{veth}" jump incoming
 }}
}}
'''


def save(path, value):
    temporary = path.with_suffix('.new')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'w') as target:
            json.dump(value, target, sort_keys=True); target.flush(); os.fsync(target.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists(): temporary.unlink()


def read_private_state(journal):
    journal = Path(journal)
    info = journal.lstat()
    if (not S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_mode & 0o077
            or info.st_uid != os.geteuid() or info.st_size > 1048576):
        raise ValueError('UNTRUSTED_PROBE_STATE')
    return json.loads(journal.read_text())


def read_state(node, marker, journal, *, accepted_prior_fingerprint=None):
    validate_marker(marker)
    if accepted_prior_fingerprint is not None and not re.fullmatch(r'[0-9a-f]{64}', accepted_prior_fingerprint):
        raise ValueError('INVALID_PRIOR_FINGERPRINT')
    previous = read_private_state(journal)
    allowed = {getattr(node, 'fingerprint', None)}
    if accepted_prior_fingerprint is not None: allowed.add(accepted_prior_fingerprint)
    if previous['marker'] != marker or previous.get('vmid') != VMID or previous['fingerprint'] not in allowed:
        raise ValueError('PROBE_REQUEST_CHANGED')
    return previous


def retire_failed_workspace(node, marker, journal, *, root=Path('/')):
    """Retirar sólo directorios vacíos dejados por una extracción fallida identificada."""
    validate_marker(marker)
    previous = read_private_state(journal)
    result = previous.get('result', {})
    if (previous.get('marker') != marker or previous.get('vmid') != VMID
            or previous.get('phase') != 'creating' or result.get('state') != 'probe_failed'
            or result.get('resource_absent') is not True or not node.absent()):
        raise ValueError('PREVIOUS_PROBE_NOT_RETIRED')
    workspace = root / f'var/lib/lxc/{VMID}'
    paths = [workspace, workspace / 'rootfs']
    mountpoints = [line.split()[4] for line in Path('/proc/self/mountinfo').read_text().splitlines()]
    if any(m == str(workspace) or m.startswith(str(workspace) + '/') for m in mountpoints):
        raise ValueError('WORKSPACE_STILL_MOUNTED')
    for path in paths:
        if not path.exists() and not path.is_symlink(): continue
        info = path.lstat()
        if not S_ISDIR(info.st_mode) or info.st_uid != os.geteuid():
            raise ValueError('UNTRUSTED_WORKSPACE')
        entries = set(p.name for p in path.iterdir())
        if entries - ({'rootfs'} if path == workspace else set()):
            raise ValueError('WORKSPACE_NOT_EMPTY')
    # rmdir nunca elimina contenido; una carrera/no vaciedad detiene la recuperación.
    for path in reversed(paths):
        if path.exists(): path.rmdir()


def reconcile_probe(node, marker, journal, *, accepted_prior_fingerprint=None):
    """Sólo retirar recursos propios de una operación existente; nunca crear/arrancar."""
    previous = read_state(node, marker, journal, accepted_prior_fingerprint=accepted_prior_fingerprint)
    if previous.get('result', {}).get('resource_absent') is True:
        return previous['result']
    try:
        existing = node.config()
        if existing is not None:
            if existing.get('marker') != marker: raise ValueError('IDENTITY_MISMATCH')
            node.cleanup(marker)
        if not node.absent(): raise ValueError('ABSENCE_NOT_CONFIRMED')
        node.remove_firewall(marker)
        result = {'state': 'probe_cleaned', 'resource_absent': True, 'profiles_enabled': []}
    except (OSError, ValueError, subprocess.SubprocessError):
        result = {'state': 'cleanup_pending', 'resource_absent': False, 'profiles_enabled': []}
    save(Path(journal), {**previous, 'result': result})
    return result


def execute_probe(node, marker, journal):
    validate_marker(marker)
    journal = Path(journal)
    fingerprint = getattr(node, 'fingerprint', None)
    if journal.exists() or journal.is_symlink():
        previous = read_state(node, marker, journal)
        if 'result' in previous:
            return previous['result']
        # Una interrupción exige reconciliación; nunca repetir create a ciegas.
        raise ValueError('PROBE_RECONCILIATION_REQUIRED')
    state = {'marker': marker, 'fingerprint': fingerprint, 'phase': 'planned', 'vmid': VMID}
    save(journal, state)
    existing = node.config()
    if existing is not None:
        result = {'state': 'probe_blocked', 'code': 'VMID_OCCUPIED', 'resource_absent': False}
        save(journal, {**state, 'result': result}); return result
    observations = {}
    passed = False
    failure = 'PROBE_NOT_CONFIRMED'
    try:
        node.require_prerequisites()
        state['phase'] = 'creating'; save(journal, state)
        node.create(marker)
        state['phase'] = 'firewall'; save(journal, state)
        node.install_firewall(marker)
        state['phase'] = 'features'; save(journal, state)
        node.configure_features(marker)
        state['phase'] = 'starting'; save(journal, state)
        node.start(marker)
        state['phase'] = 'probing'; save(journal, state)
        observations = node.probe(marker)
        passed = True
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        safe_codes = {'NO_SPACE', 'NO_MEMORY', 'NO_CPU', 'BASE_HASH_REQUIRED', 'NODE_PREREQUISITES_NOT_CONFIRMED',
                      'PROBE_ADDRESS_OCCUPIED', 'IDENTITY_MISMATCH', 'GUEST_MUST_BE_STOPPED',
                      'FEATURES_NOT_CONFIRMED', 'UNSAFE_APPARMOR', 'UNEXPECTED_BRIDGE_PORT',
                      'GUEST_PROBE_FAILED', 'FIREWALL_COUNTERS_NOT_CONFIRMED'}
        failure = str(error) if str(error) in safe_codes else 'INFRASTRUCTURE_NOT_CONFIRMED'
        guest_phase = getattr(node, 'failed_guest_phase', None)
        if guest_phase in {'prepare_runtime', 'isolation', 'public_pull', 'private_pull', 'application'}:
            observations = {'guest_failed_phase': guest_phase}
    try:
        existing = node.config()
        if existing is not None:
            if existing.get('marker') != marker:
                raise ValueError('IDENTITY_MISMATCH')
            node.cleanup(marker)
        absent = node.absent()
        if not absent:
            raise ValueError('ABSENCE_NOT_CONFIRMED')
        node.remove_firewall(marker)
        result = {'state': 'probe_passed' if passed else 'probe_failed',
                  'resource_absent': True, 'observations': observations, 'profiles_enabled': []}
        if not passed: result.update(code=failure, phase=state['phase'])
    except (OSError, ValueError, subprocess.SubprocessError):
        result = {'state': 'cleanup_pending', 'resource_absent': False,
                  'profiles_enabled': [], 'code': 'RECONCILIATION_REQUIRED', 'phase': state['phase']}
    save(journal, {**state, 'result': result})
    return result


def command(args, *, data=None, capture=False, timeout=30, child_umask=0o077):
    result = subprocess.run(args, input=data, stdin=None if data is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        timeout=timeout, check=True, umask=child_umask)
    if capture:
        if len(result.stdout) > 1048576: raise ValueError('PROBE_OUTPUT_LIMIT')
        return result.stdout
    return b''


def pvesh(path):
    return json.loads(command(['/usr/bin/pvesh', 'get', path, '--output-format', 'json'], capture=True))


def require_unused_address(address):
    """ARP de detección: lee sólo cabeceras ARP, nunca contenido de conexiones."""
    mac = bytes.fromhex(Path('/sys/class/net/vmbr0/address').read_text().strip().replace(':', ''))
    ip = socket.inet_aton(address)
    frame = b'\xff' * 6 + mac + struct.pack('!HHHBBH', 0x0806, 1, 0x0800, 6, 4, 1)
    frame += mac + b'\x00' * 4 + b'\x00' * 6 + ip
    with socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(0x0806)) as probe:
        probe.bind(('vmbr0', 0)); probe.settimeout(.2)
        for _ in range(3):
            probe.send(frame)
            until = time.monotonic() + .3
            while time.monotonic() < until:
                try: reply = probe.recv(42)
                except TimeoutError: break
                if len(reply) == 42 and reply[28:32] == ip:
                    raise ValueError('PROBE_ADDRESS_OCCUPIED')


class Node:
    def __init__(self, bootstrap, manifest, config, marker):
        bootstrap.validate_config(manifest, config)
        self.bootstrap, self.config_data, self.manifest, self.marker = bootstrap, config, manifest, marker
        self.profile = next(p for p in manifest['profiles'] if p['id'] == 'docker-ubuntu24')
        slot = config['network']['slots'][0]
        self.address, self.mac = slot['address'], slot['mac']
        self.rules = firewall_policy(marker, self.address, self.mac)
        self.table = 'nap011_' + UUID(marker['run_id']).hex
        self.program = Path(__file__).with_name('guest_docker_probe.py').read_bytes()
        public = {'manifest': manifest, 'slot': slot, 'policy': self.rules,
                  'registry_ca': config['registry']['ca_pem'], 'program': self.program.decode()}
        self.fingerprint = hashlib.sha256(json.dumps(public, sort_keys=True).encode() + Path(__file__).read_bytes()).hexdigest()

    def require_prerequisites(self):
        inventory = self.bootstrap.preflight.collect_node(self.manifest)
        if not self.bootstrap.preflight.evaluate(self.manifest, inventory)['node_prerequisites_ok']:
            raise ValueError('NODE_PREREQUISITES_NOT_CONFIRMED')
        if self.profile['base_sha256'] is None:
            raise ValueError('BASE_HASH_REQUIRED')
        status = pvesh('/nodes/proxmox/storage/local-lvm/status')
        if status.get('avail', 0) < 10 * GI_B: raise ValueError('NO_SPACE')
        available = next(int(line.split()[1]) * 1024 for line in Path('/proc/meminfo').read_text().splitlines()
                         if line.startswith('MemAvailable:'))
        if available < 3 * GI_B: raise ValueError('NO_MEMORY')
        resources = pvesh('/cluster/resources')
        used_cpus = sum(r.get('maxcpu', 0) for r in resources if r.get('type') in {'lxc', 'qemu'}
                        and r.get('node') == NODE and r.get('status') == 'running')
        if used_cpus + 2 > (os.cpu_count() or 0): raise ValueError('NO_CPU')
        require_unused_address(self.address)
        command(['/usr/sbin/nft', '-c', '-f', '-'], data=self.rules.encode())

    def config(self):
        guests = pvesh('/nodes/proxmox/lxc')
        if not any(int(g['vmid']) == VMID for g in guests): return None
        # pct config codifica description para mostrarla; JSON nativo conserva el marcador.
        fields = pvesh(f'/nodes/proxmox/lxc/{VMID}/config')
        if not isinstance(fields, dict): raise ValueError('INVALID_PVE_CONFIGURATION')
        try: marker = json.loads(fields.get('description', '{}'))
        except (ValueError, TypeError): marker = None
        return {'marker': marker, 'unprivileged': fields.get('unprivileged'), 'fields': fields}

    def owned(self, marker):
        value = self.config()
        if value is None or value['marker'] != marker or str(value['unprivileged']) != '1':
            raise ValueError('IDENTITY_MISMATCH')
        return value['fields']

    def create(self, marker):
        # PVE crea directorios que luego debe recorrer el UID mapeado del LXC.
        # Sólo su subproceso usa 022; el journal, paquete y secretos conservan 077/0600.
        command(['/usr/sbin/pct', 'create', str(VMID), 'local:vztmpl/' + self.profile['base'],
            '--hostname', 'nap011-docker-spike', '--description', json.dumps(marker, separators=(',', ':')),
            '--rootfs', 'local-lvm:8', '--memory', '1024', '--swap', '0', '--cores', '2',
            '--unprivileged', '1', '--start', '0', '--nameserver', '172.16.36.2',
            '--net0', f'name=eth0,bridge=vmbr0,hwaddr={self.mac},ip={self.address}/24,gw=172.16.36.2,firewall=0'],
            timeout=180, child_umask=0o022)
        self.owned(marker)

    def install_firewall(self, marker):
        self.owned(marker)
        command(['/usr/sbin/nft', '-f', '-'], data=self.rules.encode())

    def configure_features(self, marker):
        self.owned(marker)
        if b'stopped' not in command(['/usr/sbin/pct', 'status', str(VMID)], capture=True):
            raise ValueError('GUEST_MUST_BE_STOPPED')
        command(['/usr/sbin/pct', 'set', str(VMID), '--features', 'nesting=1,keyctl=1'])

    def start(self, marker):
        cfg = self.owned(marker)
        if cfg.get('features') != 'keyctl=1,nesting=1' and cfg.get('features') != 'nesting=1,keyctl=1':
            raise ValueError('FEATURES_NOT_CONFIRMED')
        if any('unconfined' in str(v) for k, v in cfg.items() if 'apparmor' in k or k == 'lxc'):
            raise ValueError('UNSAFE_APPARMOR')
        command(['/usr/sbin/pct', 'start', str(VMID)], timeout=90, child_umask=0o022)
        master = Path(f'/sys/class/net/veth{VMID}i0/master')
        if not master.exists() or master.resolve().name != 'vmbr0':
            raise ValueError('UNEXPECTED_BRIDGE_PORT')

    def probe(self, marker):
        self.owned(marker)
        confinement = command(['/usr/sbin/pct', 'exec', str(VMID), '--', 'cat', '/proc/1/attr/current'], capture=True)
        if b'unconfined' in confinement or not confinement.startswith(b'lxc-'):
            raise ValueError('UNSAFE_APPARMOR')
        # Todas las instalaciones quedan dentro de este guest sin datos académicos.
        command(['/usr/sbin/pct', 'exec', str(VMID), '--', 'passwd', '-l', 'root'])
        for args in [['apt-get', 'update', '-qq'],
                     ['apt-get', '-y', '--no-install-recommends', 'install', 'python3', 'ca-certificates', 'docker.io']]:
            command(['/usr/sbin/pct', 'exec', str(VMID), '--', 'env', 'DEBIAN_FRONTEND=noninteractive', *args], timeout=480)
        payload = json.dumps({'registry': self.config_data['registry']}).encode()
        result = command(['/usr/sbin/pct', 'exec', str(VMID), '--', 'python3', '-c', self.program.decode()],
                         data=payload, capture=True, timeout=480)
        data = json.loads(result)
        if data.get('state') != 'guest_probe_passed':
            phase = data.get('phase')
            if phase in {'prepare_runtime', 'isolation', 'public_pull', 'private_pull', 'application'}:
                self.failed_guest_phase = phase
                print('Ensayo detenido en: ' + phase, file=sys.stderr, flush=True)
            raise ValueError('GUEST_PROBE_FAILED')
        rules = json.loads(command(['/usr/sbin/nft', '-j', 'list', 'table', 'bridge', self.table], capture=True))
        counters = {}
        for entry in rules['nftables']:
            rule = entry.get('rule', {})
            if rule.get('comment') in {'nap011_node_block', 'nap011_peer_block'}:
                counters[rule['comment']] = sum(v.get('counter', {}).get('packets', 0) for v in rule.get('expr', []))
        if any(counters.get(name, 0) < 1 for name in ['nap011_node_block', 'nap011_peer_block']):
            raise ValueError('FIREWALL_COUNTERS_NOT_CONFIRMED')
        data['external_firewall_counters'] = counters
        return data

    def cleanup(self, marker):
        self.owned(marker)
        status = command(['/usr/sbin/pct', 'status', str(VMID)], capture=True)
        if b'running' in status: command(['/usr/sbin/pct', 'stop', str(VMID)], timeout=60)
        self.owned(marker)
        command(['/usr/sbin/pct', 'destroy', str(VMID)], timeout=90)

    def absent(self):
        if self.config() is not None: return False
        volumes = pvesh('/nodes/proxmox/storage/local-lvm/content')
        return not any(f'vm-{VMID}-' in v.get('volid', '') for v in volumes)

    def remove_firewall(self, marker):
        # Tabla propia por UUID; nunca flush ni cambios de reglas de otros invitados.
        value = pvesh('/nodes/proxmox/lxc')
        if any(int(g['vmid']) == VMID for g in value): raise ValueError('ABSENCE_NOT_CONFIRMED')
        tables = json.loads(command(['/usr/sbin/nft', '-j', 'list', 'tables'], capture=True))
        if not any(t.get('table', {}).get('name') == self.table for t in tables['nftables']): return
        info = json.loads(command(['/usr/sbin/nft', '-j', 'list', 'table', 'bridge', self.table], capture=True))
        entry = next(t['table'] for t in info['nftables'] if 'table' in t)
        if entry.get('comment') != marker['run_id']: raise ValueError('FIREWALL_IDENTITY_MISMATCH')
        command(['/usr/sbin/nft', 'delete', 'table', 'bridge', self.table])


def main():
    import importlib.util
    spec = importlib.util.spec_from_file_location('nap011_bootstrap', Path(__file__).with_name('preparar_entorno.py'))
    bootstrap = importlib.util.module_from_spec(spec); spec.loader.exec_module(bootstrap)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=Path(__file__).with_name('candidatos.json'))
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--cleanup-only', action='store_true')
    parser.add_argument('--retire-failed-run')
    parser.add_argument('--accepted-prior-fingerprint')
    args = parser.parse_args()
    marker = {'purpose': PURPOSE, 'run_id': args.run_id}
    try:
        validate_marker(marker)
        node = Node(bootstrap, bootstrap.preflight.read_json(args.manifest),
                    bootstrap.preflight.read_json(args.config), marker)
        if args.cleanup_only and not args.apply: raise ValueError('APPLY_REQUIRED')
        if args.accepted_prior_fingerprint is not None:
            if not args.cleanup_only or not re.fullmatch(r'[0-9a-f]{64}', args.accepted_prior_fingerprint):
                raise ValueError('INVALID_PRIOR_FINGERPRINT')
        if args.retire_failed_run:
            validate_marker({'purpose': PURPOSE, 'run_id': args.retire_failed_run})
            if not args.apply or args.cleanup_only or args.retire_failed_run == args.run_id:
                raise ValueError('INVALID_REPLACEMENT_PROBE')
        if not args.apply:
            result = {'state': 'plan_without_changes', 'vmid': VMID, 'profiles_enabled': []}
        else:
            if os.geteuid() != 0: raise ValueError('ROOT_REQUIRED')
            directory = Path('/var/lib/nap-lab011')
            bootstrap.safe_directory(directory)
            lock = os.open(directory / '.docker-spike.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            try:
                info = os.fstat(lock)
                if not S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_nlink != 1 or info.st_mode & 0o077:
                    raise ValueError('UNTRUSTED_PROBE_LOCK')
                fcntl.flock(lock, fcntl.LOCK_EX)
                if args.retire_failed_run:
                    retire_failed_workspace(node, {'purpose': PURPOSE, 'run_id': args.retire_failed_run},
                                            directory / (args.retire_failed_run + '.json'))
                if args.cleanup_only:
                    result = reconcile_probe(node, marker, directory / (args.run_id + '.json'),
                                             accepted_prior_fingerprint=args.accepted_prior_fingerprint)
                else:
                    result = execute_probe(node, marker, directory / (args.run_id + '.json'))
            finally: os.close(lock)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result['state'] in {'probe_passed', 'probe_cleaned', 'plan_without_changes'} else 2
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        safe_codes = {'PREVIOUS_PROBE_NOT_RETIRED', 'WORKSPACE_STILL_MOUNTED', 'UNTRUSTED_WORKSPACE',
                      'WORKSPACE_NOT_EMPTY', 'PROBE_RECONCILIATION_REQUIRED', 'PROBE_REQUEST_CHANGED',
                      'UNTRUSTED_PROBE_STATE', 'UNTRUSTED_PROBE_LOCK', 'ROOT_REQUIRED'}
        code = str(error) if str(error) in safe_codes else 'INFRASTRUCTURE_NOT_CONFIRMED'
        print(json.dumps({'state': 'probe_not_confirmed', 'code': code, 'profiles_enabled': [], 'vmid': VMID}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
