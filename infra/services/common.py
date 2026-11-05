"""Runtime guest de biblioteca estándar, incluido en el bundle verificado."""
from contextlib import contextmanager
import fcntl
import hashlib
import hmac
import ipaddress
import json
import os
import re
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile


CONSOLE_UNITS = ['console-getty.service', 'container-getty@.service', 'getty@.service', 'serial-getty@.service']
CONSOLE_LOGIN = "[Service]\nExecStart=\nExecStart=-/sbin/agetty -o '-p -- \\u' --noclear --keep-baud - 115200,38400,9600 $TERM\n"


class GuestError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class GuestCommandError(GuestError):
    """El proceso terminó con un código; no conserva salida, argv ni secretos."""
    def __init__(self, returncode):
        self.returncode = returncode
        super().__init__('BOOTSTRAP_FAILED')


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


class GuestSystem:
    def __init__(self, root=Path('/')):
        self.root = Path(root)
        self.forbidden_arguments = set()

    def path(self, relative):
        path = Path(relative)
        if path.is_absolute() or '..' in path.parts:
            raise GuestError('INVALID_REQUEST')
        current = self.root
        for part in path.parts:
            current /= part
            if current.is_symlink():
                raise GuestError('UNSUPPORTED_GUEST')
        return self.root / path

    def read(self, relative):
        try:
            return self.path(relative).read_text()
        except FileNotFoundError:
            return ''

    def write(self, relative, content, *, mode=0o600):
        path = self.path(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='.nap-', dir=path.parent)
        try:
            os.fchmod(fd, mode)
            with os.fdopen(fd, 'w') as output:
                output.write(content)
                output.flush(); os.fsync(output.fileno())
            os.replace(temporary, path)
            parent_fd = os.open(path.parent, os.O_DIRECTORY)
            try:
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def run(self, argv, *, input=None, timeout=60, env=None):
        if (not isinstance(argv, list) or not argv or not str(argv[0]).startswith('/')
            or any(secret and secret in str(arg) for secret in self.forbidden_arguments for arg in argv)):
            raise GuestError('INVALID_REQUEST')
        try:
            result = subprocess.run(argv, input=input, text=True, check=True, timeout=timeout,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C.UTF-8', **(env or {})})
            if len(result.stdout.encode()) > 65536:
                raise GuestError('UNCONFIRMED')
            return result.stdout
        except subprocess.CalledProcessError as exc:
            raise GuestCommandError(exc.returncode) from None
        except (OSError, subprocess.SubprocessError):
            # No volcar stdout/stderr ni la representación de una excepción de
            # subprocess: pueden contener datos de configuración privados.
            raise GuestError('BOOTSTRAP_FAILED') from None

    def account(self, name):
        for line in self.read('etc/passwd').splitlines():
            fields = line.split(':')
            if len(fields) == 7 and fields[0] == name:
                return {'uid': int(fields[2]), 'shell': fields[6]}
        return None

    def shadow(self, name):
        for line in self.read('etc/shadow').splitlines():
            fields = line.split(':')
            if len(fields) == 9 and fields[0] == name:
                return fields[1]
        return None

    def password_matches(self, name, secret):
        import crypt  # Ubuntu 24.04/Python 3.12 de la receta fijada.
        stored = self.shadow(name)
        return bool(stored and hmac.compare_digest(crypt.crypt(secret, stored) or '', stored))


def configure_console(system=None):
    system = system or GuestSystem()
    for unit in CONSOLE_UNITS:
        system.write('etc/systemd/system/' + unit + '.d/zz-nap-login.conf', CONSOLE_LOGIN, mode=0o644)
    system.run(['/usr/bin/passwd', '--lock', 'root'])


def network_configuration(request):
    """Solo material del perfil institucional inyectado por el runner root."""
    value = request.get('infrastructure')
    try:
        public_fields = {'host', 'address', 'client_cidrs'}
        tls_fields = {'tls_certificate', 'tls_private_key', 'tls_ca'}
        bootstrap = request.get('action') == 'bootstrap'
        if not isinstance(value, dict) or set(value) != (public_fields | tls_fields if bootstrap else public_fields):
            raise ValueError()
        host = value['host']
        if not isinstance(host, str) or len(host) > 253 or '.' not in host or any(
            not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in host.split('.')):
            raise ValueError()
        address = ipaddress.ip_address(value['address'])
        if address.is_loopback or address.is_unspecified or address.is_multicast or address.is_link_local:
            raise ValueError()
        cidrs = value['client_cidrs']
        if not isinstance(cidrs, list) or not 1 <= len(cidrs) <= 32 or len(set(cidrs)) != len(cidrs):
            raise ValueError()
        for cidr in cidrs:
            network = ipaddress.ip_network(cidr, strict=True)
            if network.prefixlen == 0 or network.is_multicast or network.is_unspecified:
                raise ValueError()
        for name in tls_fields if bootstrap else []:
            if not isinstance(value[name], str) or not 16 <= len(value[name].encode()) <= 16384 or '\x00' in value[name]:
                raise ValueError()
        return dict(value)
    except (ValueError, TypeError, KeyError):
        raise GuestError('INVALID_NETWORK_PROFILE') from None


def bind_network(context, network):
    public = {name: network[name] for name in ['host', 'address', 'client_cidrs']}
    digest = hashlib.sha256(canonical(public).encode()).hexdigest()
    previous = context.state.get('network_sha256')
    if previous and previous != digest:
        raise GuestError('IDENTITY_MISMATCH')
    if not previous:
        if context.request['action'] != 'bootstrap':
            raise GuestError('UNCONFIRMED')
        context.state['network_sha256'] = digest
        context.save()


def install_tls(system, network, directory, *, owner):
    target = system.path(directory)
    target.mkdir(parents=True, mode=0o700, exist_ok=True)
    target.chmod(0o700)
    system.forbidden_arguments.add(network['tls_private_key'])
    for name, field in [('server.crt', 'tls_certificate'), ('server.key', 'tls_private_key'), ('ca.crt', 'tls_ca')]:
        system.write(directory + '/' + name, network[field])
    # Comprobar cadena, vigencia, nombre y correspondencia de clave; no emitir
    # certificados ni adoptar el snakeoil de la imagen.
    prefix = '/' + directory
    system.run(['/usr/bin/openssl', 'verify', '-purpose', 'sslserver', '-verify_hostname', network['host'],
        '-CAfile', prefix + '/ca.crt', prefix + '/server.crt'])
    system.run(['/usr/bin/openssl', 'x509', '-in', prefix + '/server.crt', '-noout', '-checkend', '86400'])
    public = system.run(['/usr/bin/openssl', 'x509', '-in', prefix + '/server.crt', '-noout', '-pubkey'])
    private_public = system.run(['/usr/bin/openssl', 'pkey', '-in', prefix + '/server.key', '-pubout'])
    if not public.strip() or not hmac.compare_digest(public.strip(), private_public.strip()):
        raise GuestError('INVALID_NETWORK_PROFILE')
    system.run(['/usr/bin/chown', '--recursive', '--no-dereference', owner, prefix])


def _identity(request):
    keys = ['cluster_uuid', 'resource_uuid', 'node', 'vmid', 'pool', 'definition_key',
        'definition_version', 'definition_sha256', 'bundle_sha256', 'network_profile_id']
    try:
        value = {key: request[key] for key in keys}
        value['nonce_sha256'] = hashlib.sha256(request['nonce'].encode()).hexdigest()
        return value
    except (KeyError, TypeError, AttributeError):
        raise GuestError('INVALID_REQUEST') from None


class GuestContext:
    def __init__(self, system, request, state):
        self.system, self.request, self.state = system, request, state
        self.steps = state.setdefault('steps', {})

    def save(self):
        self.system.write('var/lib/nap/bootstrap.json', canonical(self.state))

    def mark(self, name, status):
        self.steps[name] = status
        self.save()

    def step(self, name, action):
        if self.steps.get(name) != 'completed':
            self.mark(name, 'started')
            action()
            self.mark(name, 'completed')


@contextmanager
def _bootstrap_lock(system):
    directory = system.path('var/lib/nap')
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if directory.stat().st_mode & 0o077:
        raise GuestError('UNSUPPORTED_GUEST')
    fd = os.open(system.path('var/lib/nap/bootstrap.lock'), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise GuestError('UNCONFIRMED') from None
        yield
    finally:
        os.close(fd)


def run_product(product, request, *, system=None):
    system = system or GuestSystem()
    identity = _identity(request)
    action = request.get('action')
    if action not in {'bootstrap', 'inspect', 'verify'}:
        raise GuestError('INVALID_REQUEST')
    if not isinstance(request.get('parameters', {}), dict) or not set(request.get('parameters', {})) <= set(product.parameters):
        raise GuestError('INVALID_REQUEST')
    parameters = request.get('parameters', {})
    if any(not isinstance(value, str) or not value.strip() or len(value) > (254 if name == 'teacher_email' else 100)
        or any(ord(c) < 32 for c in value) for name, value in parameters.items()):
        raise GuestError('INVALID_REQUEST')
    if 'database_name' in parameters and (not re.fullmatch(r'[a-z][a-z0-9_]{0,62}', parameters['database_name'])
        or parameters['database_name'] in {'postgres', 'template0', 'template1'}):
        raise GuestError('INVALID_REQUEST')
    parameters_sha = hashlib.sha256(canonical(parameters).encode()).hexdigest()
    if action != 'bootstrap':
        if 'secrets' in request:
            raise GuestError('INVALID_REQUEST')
        stored = system.read('var/lib/nap/bootstrap.json')
        state = json.loads(stored) if stored else {}
        if state and state.get('identity') != identity:
            raise GuestError('IDENTITY_MISMATCH')
        if state and state.get('parameters_sha256') != parameters_sha:
            raise GuestError('IDEMPOTENCY_CONFLICT')
        if not state.get('completed'):
            return {'ready': False, 'bootstrap_completed': False}
        context = GuestContext(system, request, state)
        return product.verify(context) if action == 'verify' else product.inspect(context)
    values = request.get('secrets', {})
    if (not isinstance(values, dict) or set(values) != set(product.secret_fields)
        or any(not isinstance(value, str) or not 20 <= len(value) <= 512 or '\n' in value or '\r' in value or '\x00' in value for value in values.values())):
        raise GuestError('INVALID_REQUEST')
    system.forbidden_arguments.update(values.values())
    with _bootstrap_lock(system):
        stored = system.read('var/lib/nap/bootstrap.json')
        state = json.loads(stored) if stored else {}
        if state and state.get('identity') != identity:
            raise GuestError('IDENTITY_MISMATCH')
        key_path = system.path('var/lib/nap/bootstrap.key')
        if not key_path.exists():
            if state:
                raise GuestError('UNCONFIRMED')
            system.write('var/lib/nap/bootstrap.key', secrets.token_hex(32))
        if key_path.stat().st_mode & 0o077:
            raise GuestError('UNSUPPORTED_GUEST')
        key = bytes.fromhex(system.read('var/lib/nap/bootstrap.key'))
        if len(key) != 32:
            raise GuestError('UNCONFIRMED')
        frozen = {name: value for name, value in request.items() if name not in {'operation_id', 'action'}}
        fingerprint = hmac.new(key, canonical(frozen).encode(), hashlib.sha256).hexdigest()
        if state and not hmac.compare_digest(state.get('request_hmac', ''), fingerprint):
            raise GuestError('IDEMPOTENCY_CONFLICT')
        state = state or {'identity': identity, 'request_hmac': fingerprint, 'parameters_sha256': parameters_sha, 'steps': {}, 'completed': False}
        context = GuestContext(system, request, state)
        context.save()
        if not state['completed']:
            product.prepare(context)
            result = product.verify(context)
            if result.get('ready') is not True:
                raise GuestError('PROBE_FAILED')
            state['completed'] = True
            context.save()
        return product.inspect(context)


def main(product):
    def pairs(items):
        result = {}
        for name, value in items:
            if name in result:
                raise GuestError('INVALID_REQUEST')
            result[name] = value
        return result
    def invalid_number(value):
        raise GuestError('INVALID_REQUEST')
    try:
        raw = sys.stdin.buffer.read(65537)
        if len(raw) > 65536:
            raise GuestError('INVALID_REQUEST')
        request = json.loads(raw, object_pairs_hook=pairs, parse_float=invalid_number, parse_constant=invalid_number)
        allowed = {'protocol', 'operation_id', 'action', 'cluster_uuid', 'resource_uuid', 'node', 'vmid', 'pool',
            'nonce', 'definition_key', 'definition_version', 'definition_sha256', 'bundle_sha256',
            'network_profile_id', 'parameters', 'secrets', 'infrastructure'}
        if not isinstance(request, dict) or not set(request) <= allowed or os.geteuid() != 0:
            raise GuestError('INVALID_REQUEST')
        result = run_product(product, request)
        print(canonical(result))
    except GuestError as exc:
        print(canonical({'ready': False, 'error': {'code': exc.code, 'message': 'La preparación o comprobación no pudo confirmarse'}}))
        raise SystemExit(1)
    except Exception:
        print(canonical({'ready': False, 'error': {'code': 'BOOTSTRAP_FAILED', 'message': 'Resultado no confirmado'}}))
        raise SystemExit(1)
