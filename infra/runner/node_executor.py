"""Adaptador local PVE: argumentos fijos, identidad por cada efecto y deadline."""
import hashlib
import ipaddress
import json
import os
import re
from pathlib import Path
import selectors
import signal
import subprocess
import tempfile
import time

if __package__:
    from app.schemas.guest_runner import RunnerError, canonical, parse_json, safe_result
    from infra.runner.nap_guest_runner import trusted_file
else:
    from protocol import RunnerError, canonical, parse_json, safe_result
    from nap_guest_runner import trusted_file


# Código constante del wrapper, nunca código recibido por JSON. Todos los
# archivos temporales quedan dentro del LXC no privilegiado y bajo root.
STAGE = r'''
import os, pathlib, stat
path = pathlib.Path('/run/nap-runner')
if path.exists() or path.is_symlink():
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
        raise SystemExit(1)
else:
    path.mkdir(mode=0o700)
bundle = path / 'bundle.tar.gz'
if bundle.is_symlink() or (bundle.exists() and not bundle.is_file()):
    raise SystemExit(1)
bundle.unlink(missing_ok=True)
'''

GUEST_CALL = r'''
import hashlib, io, json, os, pathlib, shutil, subprocess, sys, tarfile, tempfile
payload = json.loads(sys.stdin.buffer.read(131073))
request, product = payload['request'], payload['product']
if product not in {'linux','postgresql','bookstack','drawio'}:
    raise SystemExit(1)
bundle = pathlib.Path('/run/nap-runner/bundle.tar.gz')
fd = os.open(bundle, os.O_RDONLY | os.O_NOFOLLOW)
try:
    with os.fdopen(fd, 'rb', closefd=False) as source:
        data = source.read(2097153)
finally:
    os.close(fd)
if len(data) > 2097152 or hashlib.sha256(data).hexdigest() != request['bundle_sha256']:
    raise SystemExit(1)
allowed = {'common.py','bootstrap.py'} | ({'configure.php'} if product == 'bookstack' else set())
with tempfile.TemporaryDirectory(prefix='recipe-', dir='/run/nap-runner') as temporary:
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
        members = archive.getmembers()
        if len(members) != len(allowed) or {item.name for item in members} != allowed or sum(item.size for item in members) > 1048576:
            raise SystemExit(1)
        for item in members:
            if not item.isfile():
                raise SystemExit(1)
            target = pathlib.Path(temporary) / item.name
            target.write_bytes(archive.extractfile(item).read())
            target.chmod(0o500)
    try:
        result = subprocess.run(['/usr/bin/python3', temporary + '/bootstrap.py'],
            input=json.dumps(request).encode(), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=155, env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LANG':'C.UTF-8'})
        if result.returncode != 0 or len(result.stdout) > 65536:
            raise SystemExit(1)
        sys.stdout.buffer.write(result.stdout)
    finally:
        bundle.unlink(missing_ok=True)
'''


def parse_system_json(raw, *, limit=65536):
    """Parsear JSON de herramientas del sistema (pvesh/ip) que incluyen métricas float."""
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError()
            result[key] = value
        return result
    def invalid(value):
        raise ValueError()
    try:
        if not isinstance(raw, bytes) or len(raw) > limit:
            raise ValueError()
        return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=invalid)
    except (ValueError, TypeError, RecursionError):
        raise RunnerError('UNCONFIRMED') from None


def bounded_command(argv, *, input=None, timeout=30, limit=2097152, accepted_codes=(0,)):
    """Drenar stdout con límite, sin capturar stderr ni usar un shell."""
    process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        start_new_session=True, env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C.UTF-8'})
    output, pending = bytearray(), memoryview(input or b'')
    deadline = time.monotonic() + timeout
    try:
        with selectors.DefaultSelector() as selector:
            os.set_blocking(process.stdout.fileno(), False)
            selector.register(process.stdout, selectors.EVENT_READ)
            if pending:
                os.set_blocking(process.stdin.fileno(), False)
                selector.register(process.stdin, selectors.EVENT_WRITE)
            else:
                process.stdin.close()
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RunnerError('DEADLINE_EXCEEDED')
                for key, events in selector.select(min(remaining, 1)):
                    if key.fileobj is process.stdout:
                        chunk = os.read(key.fd, 16384)
                        if not chunk:
                            selector.unregister(key.fileobj)
                        output.extend(chunk)
                        if len(output) > limit:
                            raise RunnerError('UNCONFIRMED')
                    else:
                        try:
                            written = os.write(key.fd, pending[:16384])
                            pending = pending[written:]
                        except BrokenPipeError:
                            pending = pending[len(pending):]
                        if not pending:
                            selector.unregister(key.fileobj); process.stdin.close()
            process.wait(timeout=max(0.01, deadline - time.monotonic()))
            if process.returncode not in accepted_codes:
                raise RunnerError('UNCONFIRMED')
            return bytes(output)
    except (OSError, subprocess.SubprocessError):
        raise RunnerError('UNCONFIRMED') from None
    finally:
        # Una conexión cortada no prueba que el proceso guest haya terminado.
        # El caller ya persistió dispatch y no vuelve a enviarlo a ciegas.
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        process.stdout.close()
        if not process.stdin.closed:
            process.stdin.close()


class NodeExecutor:
    def __init__(self, *, registry, run_command=None, local_node=None, temporary_root='/var/lib/nap-runner/tmp'):
        self.registry, self.run_command = registry, run_command or bounded_command
        self.local_node = local_node or Path(os.readlink('/etc/pve/local')).name
        self.temporary_root = Path(temporary_root).absolute()
        if self.temporary_root.resolve() != self.temporary_root:
            raise RunnerError('RUNNER_UNAVAILABLE')
        self.temporary_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.temporary_root.stat().st_mode & 0o077 or self.temporary_root.stat().st_uid not in {0, os.geteuid()}:
            raise RunnerError('RUNNER_UNAVAILABLE')
        self.deadline = time.monotonic() + 170

    def _run(self, argv, *, input=None):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise RunnerError('DEADLINE_EXCEEDED')
        return self.run_command(argv, input=input, timeout=min(remaining, 160))

    def _identity(self, request):
        if request['node'] != self.local_node:
            raise RunnerError('IDENTITY_MISMATCH')
        resources = parse_system_json(self._run(['/usr/bin/pvesh', 'get', '/cluster/resources', '--type', 'vm', '--output-format', 'json']), limit=2097152)
        matches = [row for row in resources if row.get('vmid') == request['vmid']]
        if len(matches) != 1 or matches[0].get('node') != request['node'] or matches[0].get('type') != 'lxc' or matches[0].get('pool') != request['pool']:
            raise RunnerError('IDENTITY_MISMATCH')
        path = '/nodes/' + request['node'] + '/lxc/' + str(request['vmid']) + '/config'
        config = parse_system_json(self._run(['/usr/bin/pvesh', 'get', path, '--output-format', 'json']))
        try:
            marker = parse_json(config['description'].encode())['nap']
            expected = {key: request[key] for key in ['cluster_uuid', 'resource_uuid', 'pool', 'definition_sha256', 'bundle_sha256']}
            expected['nonce_sha256'] = hashlib.sha256(request['nonce'].encode()).hexdigest()
            unprivileged = config.get('unprivileged')
            if marker != expected or not (unprivileged is True or type(unprivileged) is int and unprivileged == 1):
                raise ValueError()
        except (ValueError, KeyError, TypeError, AttributeError):
            raise RunnerError('IDENTITY_MISMATCH') from None

    def _checked(self, request, command, *, input=None):
        self._identity(request)
        try:
            return self._run(command, input=input)
        finally:
            self._identity(request)

    def _exec(self, request, argv, *, input=None):
        return self._checked(request, ['/usr/sbin/pct', 'exec', str(request['vmid']), '--', *argv], input=input)

    def _entry(self, request):
        entry = self.registry.get(request['definition_key'] + ':' + request['definition_version'])
        if not entry or entry.get('bundle_sha256') != request['bundle_sha256']:
            raise RunnerError('UNKNOWN_RECIPE')
        return entry

    def _network(self, request, entry):
        try:
            profile = entry['networks'][request['network_profile_id']]
            subnets = [ipaddress.ip_network(value, strict=True) for value in profile['subnets']]
            if not subnets or any(network.prefixlen == 0 for network in subnets):
                raise ValueError()
            rows = parse_system_json(self._exec(request, ['/usr/sbin/ip', '-json', 'address', 'show']))
            observed = {ipaddress.ip_address(item['local']) for row in rows for item in row.get('addr_info', []) if item.get('family') in {'inet', 'inet6'}}
            allowed = {address for address in observed if not address.is_loopback and not address.is_link_local
                and any(address in network for network in subnets if address.version == network.version)}
            if not allowed:
                raise ValueError()
            if entry['product'] == 'linux':
                return None, sorted(map(str, allowed))
            instance = profile['instances'][request['resource_uuid']]
            if ipaddress.ip_address(instance['address']) not in allowed:
                raise ValueError()
            network = {name: instance[name] for name in ['host', 'address']}
            network['client_cidrs'] = profile['client_cidrs']
            if request['action'] == 'bootstrap':
                for field in ['tls_certificate', 'tls_private_key', 'tls_ca']:
                    path = Path(instance[field + '_path'])
                    if field == 'tls_private_key' and path.stat().st_mode & 0o077:
                        raise ValueError()
                    network[field] = trusted_file(path, limit=16384).decode()
            return network, sorted(map(str, allowed))
        except (KeyError, ValueError, TypeError, OSError):
            raise RunnerError('NETWORK_PROFILE_UNAVAILABLE') from None

    def execute(self, request, *, bundle_path):
        entry = self._entry(request)
        bundle = trusted_file(bundle_path)
        if hashlib.sha256(bundle).hexdigest() != request['bundle_sha256']:
            raise RunnerError('DEFINITION_MISMATCH')
        network, addresses = self._network(request, entry)
        candidate = dict(request)
        if network is not None:
            candidate['infrastructure'] = network
        payload = canonical({'request': candidate, 'product': entry['product']}).encode()
        if len(payload) > 131072:
            raise RunnerError('INVALID_REQUEST')
        with tempfile.TemporaryDirectory(prefix='operation-', dir=self.temporary_root) as temporary:
            snapshot = Path(temporary) / 'bundle.tar.gz'
            snapshot.write_bytes(bundle); snapshot.chmod(0o400)
            self._exec(request, ['/usr/bin/python3', '-c', STAGE])
            self._checked(request, ['/usr/sbin/pct', 'push', str(request['vmid']), str(snapshot),
                '/run/nap-runner/bundle.tar.gz', '--perms', '0600'])
            raw = self._exec(request, ['/usr/bin/python3', '-c', GUEST_CALL], input=payload)
        result = safe_result(parse_json(raw), request)
        result['addresses'] = addresses
        if network is not None:
            if result.get('ready') is True or result.get('bootstrap_completed') is True:
                if result.get('host') != network['host'] or result.get('address') != network['address']:
                    raise RunnerError('IDENTITY_MISMATCH')
            else:
                result.update(host=network['host'], address=network['address'])
        return result

    def inspect(self, request):
        candidate = {key: value for key, value in request.items() if key != 'secrets'}
        candidate['action'] = 'inspect'
        entry = self._entry(candidate)
        result = self.execute(candidate, bundle_path=entry['bundle_path'])
        self._identity(request)
        return {**{key: request[key] for key in ['cluster_uuid', 'resource_uuid', 'node', 'vmid', 'pool', 'nonce',
            'definition_sha256', 'bundle_sha256']}, 'type': 'lxc', 'unprivileged': True, **result}


class ApplicationNodeExecutor:
    """Separate adapter for application jobs; legacy recipes remain unchanged.

    It cannot create another guest, execute a Community host script or accept
    PVE flags from the wire. Environment effects are a fixed Docker feature
    pair and exclusive host isolation on an owned, stopped, unprivileged CT.
    """
    def __init__(self, *, profiles, cluster_uuid, run_command=None, local_node=None):
        if __package__:
            from infra.applications.job import protocol as job_protocol
        else:
            from applications.job import protocol as job_protocol
        self.protocol = job_protocol
        self.profiles, self.cluster_uuid = profiles, cluster_uuid
        self.run_command = run_command or bounded_command
        self.local_node = local_node or Path(os.readlink('/etc/pve/local')).name

    def _call(self, argv, *, input=None):
        try: return self.run_command(argv, timeout=5, limit=2097152, **({'input': input} if input is not None else {}))
        except Exception: raise self.protocol.JobError('UNCONFIRMED') from None

    def platform(self):
        raw = self._call(['/usr/bin/pveversion'])
        try:
            match = re.match(rb'^pve-manager/([0-9]+\.[0-9]+(?:\.[0-9]+)?)/', raw)
            architecture = {'x86_64': 'amd64', 'aarch64': 'arm64'}[os.uname().machine]
            if not match: raise ValueError()
            return {'pve': match[1].decode('ascii'), 'kernel': os.uname().release, 'arquitectura': architecture}
        except Exception: raise self.protocol.JobError('PROFILE_UNAVAILABLE') from None

    @staticmethod
    def _features(config):
        raw = config.get('features')
        if raw in (None, ''): return {}
        if type(raw) is not str: raise ValueError()
        result = {}
        for part in raw.split(','):
            name, value = part.split('=', 1)
            if name in result: raise ValueError()
            result[name] = value
        return result

    def _configuration(self, identity):
        try:
            expected_keys = self.protocol.IDENTITY_FIELDS - {'protocol', 'nonce', 'lease_generation'} | {'nonce_sha256'}
            if type(identity) is not dict or set(identity) != expected_keys: raise ValueError()
            synthetic = {k: v for k, v in identity.items() if k != 'nonce_sha256'}
            synthetic.update(protocol=self.protocol.PROTOCOL, action='status', lease_generation=1, nonce='0'*64)
            self.protocol.parse_request(self.protocol.canonical(synthetic))
            if not re.fullmatch(r'[a-f0-9]{64}', identity['nonce_sha256']): raise ValueError()
            if identity['node'] != self.local_node or identity['cluster_uuid'] != self.cluster_uuid: raise ValueError()
            profile = self.profiles.require(identity['perfil'], cluster_uuid=self.cluster_uuid, node=self.local_node)
            resources = parse_system_json(self._call(['/usr/bin/pvesh', 'get', '/cluster/resources', '--type', 'vm', '--output-format', 'json']), limit=2097152)
            if type(resources) is not list: raise ValueError()
            matches = [row for row in resources if row.get('vmid') == identity['vmid']]
            if (len(matches) != 1 or matches[0].get('node') != self.local_node or matches[0].get('type') != 'lxc'
                    or matches[0].get('pool') != identity['pool']): raise ValueError()
            path = '/nodes/'+self.local_node+'/lxc/'+str(identity['vmid'])+'/config'
            config = parse_system_json(self._call(['/usr/bin/pvesh', 'get', path, '--output-format', 'json']))
            marker = self.protocol.strict_json(config['description'].encode(), limit=16384)
            expected = {'cluster_uuid': self.cluster_uuid, 'resource_uuid': identity['resource_uuid'],
                'nonce_sha256': identity['nonce_sha256'], 'pool': identity['pool'],
                'definition_sha256': identity['configuracion_sha256'], 'bundle_sha256': profile['policy_bundle_sha256']}
            if marker != {'nap': expected}: raise ValueError()
            unprivileged = config.get('unprivileged')
            if not (unprivileged is True or type(unprivileged) is int and unprivileged == 1): raise ValueError()
            if any(k == 'lxc' or k.startswith('lxc.') or k == 'hookscript' or re.fullmatch(r'(?:mp|dev)[0-9]+', k) for k in config): raise ValueError()
            features = self._features(config)
            if features and not (profile['origen'] == 'imagen_docker' and features == {'nesting': '1', 'keyctl': '1'}): raise ValueError()
            cores, memory = config.get('cores'), config.get('memory')
            if type(cores) is not int or type(memory) is not int: raise ValueError()
            rootfs = config.get('rootfs')
            size = re.search(r'(?:^|,)size=([0-9]+)G(?:,|$)', rootfs) if type(rootfs) is str else None
            if not size or (cores, memory, int(size[1])) not in {(1,512,4), (2,1024,8)}: raise ValueError()
            actual = {'vcpus': cores, 'ram_mb': memory, 'disk_gb': int(size[1])}
            if any(actual[k] < v for k, v in profile['minimum_resources'].items()): raise ValueError()
            return config, profile
        except self.protocol.JobError: raise
        except Exception: raise self.protocol.JobError('IDENTITY_MISMATCH') from None

    def assert_owner(self, identity):
        self._configuration(identity)
        return True

    def install_isolation(self, identity, policy):
        """Internal driver action, not a new wire action or a guest parameter.

        Exclusive table creation intentionally refuses to adopt/rewrite an
        existing table. A lost response requires reconciliation, never a flush.
        Institutional policy loading and durable recovery belong to the driver.
        """
        if __package__:
            from infra.applications.job.network import compile_policy
        else:
            from applications.job.network import compile_policy
        batch = compile_policy(policy)
        config, _ = self._configuration(identity)
        try:
            if policy['resource_uuid'] != identity['resource_uuid'] or policy['vmid'] != identity['vmid']: raise ValueError()
            entries = config['net0'].split(',')
            net = dict(item.split('=', 1) for item in entries)
            if len(net) != len(entries) or set(net) - {'name','bridge','hwaddr','ip','gw','firewall','ip6'}: raise ValueError()
            if (net.get('name') != 'eth0' or net.get('bridge') != policy['bridge']
                    or net.get('hwaddr','').lower() != policy['mac_address']
                    or net.get('ip6') not in (None, 'manual')
                    or str(ipaddress.IPv4Interface(net['ip']).ip) != policy['address']): raise ValueError()
            if any(re.fullmatch(r'net[1-9][0-9]*', k) for k in config): raise ValueError()
            status = parse_system_json(self._call(['/usr/bin/pvesh', 'get',
                '/nodes/'+self.local_node+'/lxc/'+str(identity['vmid'])+'/status/current', '--output-format', 'json']))
            if status.get('status') != 'stopped': raise ValueError()
            # Re-observe ownership immediately before the only effect. No start,
            # privilege change, nft delete/flush or shell command is permitted.
            latest, _ = self._configuration(identity)
            if latest != config: raise ValueError()
            self._call(['/usr/sbin/nft', '-f', '-'], input=batch)
            return True
        except self.protocol.JobError: raise
        except Exception: raise self.protocol.JobError('UNCONFIRMED') from None

    def enable_environment(self, identity):
        config, profile = self._configuration(identity)
        if profile['origen'] != 'imagen_docker' or self._features(config) == {'nesting': '1', 'keyctl': '1'}: return True
        path = '/nodes/'+self.local_node+'/lxc/'+str(identity['vmid'])+'/status/current'
        try:
            status = parse_system_json(self._call(['/usr/bin/pvesh', 'get', path, '--output-format', 'json']))
            if status.get('status') != 'stopped': raise self.protocol.JobError('UNCONFIRMED')
            self.assert_owner(identity)
            self._call(['/usr/sbin/pct', 'set', str(identity['vmid']), '--features', 'nesting=1,keyctl=1'])
            verified, _ = self._configuration(identity)
            if self._features(verified) != {'nesting': '1', 'keyctl': '1'}: raise self.protocol.JobError('UNCONFIRMED')
            return True
        except self.protocol.JobError: raise
        except Exception: raise self.protocol.JobError('UNCONFIRMED') from None
