"""Wrapper root cerrado; registro local y estado privado, sin shell de cliente."""
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import base64
import hashlib
import hmac
import json
import os
import re
from pathlib import Path
import secrets
import stat
import sys
import tempfile

if __package__:
    from app.schemas.guest_runner import (PROTOCOL, IDENTITY_FIELDS, PRODUCT_PARAMETERS, RunnerError,
        canonical, parse_json, parse_request, safe_result)
else:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from protocol import (PROTOCOL, IDENTITY_FIELDS, PRODUCT_PARAMETERS, RunnerError,
        canonical, parse_json, parse_request, safe_result)


def trusted_file(path, *, limit=2097152):
    path = Path(path)
    if (not path.is_absolute() or path.parent.resolve() != path.parent or not path.parent.is_dir()
        or path.parent.stat().st_mode & 0o022 or path.parent.stat().st_uid not in {0, os.geteuid()}):
        raise RunnerError('UNKNOWN_RECIPE')
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid not in {0, os.geteuid()} or info.st_mode & 0o022 or info.st_size > limit:
                raise RunnerError('UNKNOWN_RECIPE')
            with os.fdopen(fd, 'rb', closefd=False) as source:
                value = source.read(limit + 1)
            if len(value) > limit:
                raise RunnerError('UNKNOWN_RECIPE')
            return value
        finally:
            os.close(fd)
    except OSError:
        raise RunnerError('UNKNOWN_RECIPE') from None


def write_private(path, value):
    fd, temporary = tempfile.mkstemp(prefix='.nap-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as output:
            output.write(canonical(value)); output.flush(); os.fsync(output.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class Runner:
    def __init__(self, *, state_dir, registry, executor):
        self.state_dir, self.registry, self.executor = Path(state_dir).absolute(), registry, executor
        if self.state_dir.resolve() != self.state_dir:
            raise RunnerError('RUNNER_UNAVAILABLE')
        self.state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.state_dir.stat().st_uid not in {0, os.geteuid()} or self.state_dir.stat().st_mode & 0o077:
            raise RunnerError('RUNNER_UNAVAILABLE')
        key_path = self.state_dir / 'hmac.key'
        try:
            fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            try:
                os.write(fd, secrets.token_bytes(32)); os.fsync(fd)
            finally:
                os.close(fd)
        except FileExistsError:
            pass
        self.key = trusted_file(key_path, limit=32)
        if len(self.key) != 32 or key_path.stat().st_mode & 0o077:
            raise RunnerError('RUNNER_UNAVAILABLE')

    @contextmanager
    def lock(self, key):
        fd = os.open(self.state_dir / (key + '.lock'), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RunnerError('UNCONFIRMED') from None
            yield
        finally:
            os.close(fd)

    def _hmac(self, value):
        return hmac.new(self.key, canonical(value).encode(), hashlib.sha256).hexdigest()

    def _recipe(self, request):
        entry = self.registry.get(request['definition_key'] + ':' + request['definition_version'])
        if not isinstance(entry, dict) or entry.get('product') not in PRODUCT_PARAMETERS or entry.get('security_blocked'):
            raise RunnerError('UNKNOWN_RECIPE')
        if (entry.get('definition_sha256') != request['definition_sha256'] or entry.get('bundle_sha256') != request['bundle_sha256']
            or entry.get('cluster_uuid') != request['cluster_uuid'] or request['node'] not in entry.get('nodes', [])
            or request['network_profile_id'] not in entry.get('network_profile_ids', [])):
            raise RunnerError('DEFINITION_MISMATCH')
        data = trusted_file(entry.get('bundle_path', ''))
        if hashlib.sha256(data).hexdigest() != request['bundle_sha256']:
            raise RunnerError('DEFINITION_MISMATCH')
        if not set(request['parameters']) <= PRODUCT_PARAMETERS[entry['product']]:
            raise RunnerError('INVALID_REQUEST')
        secret_fields = {'linux': {'guest_password'}, 'postgresql': {'database_password'},
            'bookstack': {'teacher_password', 'database_password', 'app_key'}}[entry['product']]
        if request['action'] == 'bootstrap' and set(request['secrets']) != secret_fields:
            raise RunnerError('INVALID_REQUEST')
        return entry

    def _inspect(self, request):
        value = self.executor.inspect(request)
        if (not isinstance(value, dict) or any(value.get(key) != request[key] for key in IDENTITY_FIELDS)
            or value.get('unprivileged') is not True or value.get('type') != 'lxc'):
            raise RunnerError('IDENTITY_MISMATCH')
        return value

    def _parameters(self, request, product):
        parameters = request['parameters']
        if 'display_name' not in parameters:
            raise RunnerError('INVALID_REQUEST')
        database = parameters.get('database_name')
        if database is not None and (not re.fullmatch(r'[a-z][a-z0-9_]{0,62}', database) or database in {'postgres', 'template0', 'template1'}):
            raise RunnerError('INVALID_REQUEST')
        if product == 'bookstack':
            email = parameters.get('teacher_email', '')
            if (set(parameters) != PRODUCT_PARAMETERS[product] or parameters['locale'] not in {'es', 'en'}
                or email.lower() == 'admin@admin.com' or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email)):
                raise RunnerError('INVALID_REQUEST')
        if request['action'] == 'bootstrap':
            if any(not 20 <= len(value) <= 512 for value in request['secrets'].values()):
                raise RunnerError('INVALID_REQUEST')
            if product == 'bookstack':
                key = request['secrets']['app_key']
                try:
                    if not key.startswith('base64:') or len(base64.b64decode(key[7:], validate=True)) != 32:
                        raise ValueError()
                except ValueError:
                    raise RunnerError('INVALID_REQUEST') from None

    def _response(self, request, *, status, phase, identity, result=None, code=None):
        value = {key: request[key] for key in ['protocol', 'operation_id', 'action', 'resource_uuid']}
        value.update(status=status, phase=phase, identity_verified=identity, observed_at=datetime.now(timezone.utc).isoformat())
        if result is not None:
            value['result'] = safe_result(result, request)
        else:
            value['error'] = {'code': code or 'UNCONFIRMED', 'phase': phase, 'retryable': status in {'pending', 'unconfirmed'},
                'message': 'Resultado no confirmado; revisar la operación'}
        return value

    def handle(self, raw):
        request = {'protocol': PROTOCOL, 'operation_id': '00000000-0000-0000-0000-000000000000',
            'action': 'inspect', 'resource_uuid': '00000000-0000-0000-0000-000000000000'}
        effect, identity, phase = False, False, 'validation'
        try:
            request = parse_request(raw)
            entry = self._recipe(request)
            resource_key = self._hmac({key: request[key] for key in ['cluster_uuid', 'resource_uuid']})
            with self.lock(resource_key):
                path = self.state_dir / (resource_key + '.json')
                state = parse_json(trusted_file(path), limit=2097152) if path.exists() else {'requests': {}}
                fingerprint = self._hmac(request)
                operation_key = request['operation_id'] + ':' + request['action']
                attempt = state['requests'].get(operation_key)
                if attempt and not hmac.compare_digest(attempt['hmac'], fingerprint):
                    raise RunnerError('IDEMPOTENCY_CONFLICT')
                frozen = self._hmac({key: value for key, value in request.items() if key not in {'operation_id', 'action'}})
                if request['action'] == 'bootstrap' and state.get('bootstrap_hmac') and not hmac.compare_digest(state['bootstrap_hmac'], frozen):
                    raise RunnerError('IDEMPOTENCY_CONFLICT')
                self._parameters(request, entry['product'])
                phase = 'inspection'
                observed = self._inspect(request)
                identity = True
                if request['action'] == 'inspect':
                    # Node.inspect ya ejecutó el probe desde el bundle y volvió
                    # a comprobar propiedad. No duplicar ese trabajo de lectura.
                    result = {key: value for key, value in observed.items() if key in {'ready', 'bootstrap_completed',
                        'host', 'address', 'addresses', 'endpoint', 'port', 'username', 'database', 'checks', 'version'}}
                    state['requests'][operation_key] = {'hmac': fingerprint, 'phase': 'completed'}
                    write_private(path, state)
                    return self._response(request, status='succeeded' if result.get('ready') is True else 'pending',
                        phase='verified', identity=True, result=result)
                if request['action'] == 'bootstrap' and (state.get('bootstrap_started') or observed.get('bootstrap_completed')):
                    if not state.get('bootstrap_hmac'):
                        raise RunnerError('UNCONFIRMED')
                    if observed.get('bootstrap_completed') is True and observed.get('ready') is True:
                        result = {key: value for key, value in observed.items() if key in {'ready', 'bootstrap_completed',
                            'host', 'address', 'addresses', 'endpoint', 'port', 'username', 'database', 'checks', 'version'}}
                        return self._response(request, status='succeeded', phase='verified', identity=True, result=result)
                    raise RunnerError('UNCONFIRMED')
                state['requests'][operation_key] = {'hmac': fingerprint, 'phase': 'started'}
                if request['action'] == 'bootstrap':
                    state.update(bootstrap_hmac=frozen, bootstrap_started=True)
                write_private(path, state)
                phase, effect = 'execution', request['action'] == 'bootstrap'
                result = self.executor.execute(request, bundle_path=entry['bundle_path'])
                phase = 'verification'
                self._inspect(request)
                result = safe_result(result, request)
                if result.get('ready') is not True:
                    raise RunnerError('PROBE_FAILED')
                state['requests'][operation_key]['phase'] = 'completed'
                write_private(path, state)
                return self._response(request, status='succeeded', phase='verified', identity=True, result=result)
        except RunnerError as exc:
            if exc.code == 'IDENTITY_MISMATCH':
                identity = False
            return self._response(request, status='unconfirmed' if effect or exc.code == 'UNCONFIRMED' else 'failed',
                phase=phase, identity=identity, code=exc.code)
        except (OSError, ValueError, KeyError, TypeError, TimeoutError):
            return self._response(request, status='unconfirmed', phase=phase, identity=False, code='UNCONFIRMED')


def main():
    # Rutas fijas root; nunca opciones/entorno aportados por la cuenta SSH.
    if os.geteuid() != 0 or len(sys.argv) != 1:
        raise SystemExit(1)
    import signal
    signal.alarm(10)
    raw = sys.stdin.buffer.read(65537)
    signal.alarm(0)
    try:
        registry = parse_json(trusted_file('/etc/nap/runner/registry.json'), limit=2097152)
        from node_executor import NodeExecutor
        executor = NodeExecutor(registry=registry)
        runner = Runner(state_dir='/var/lib/nap-runner', registry=registry, executor=executor)
        response = runner.handle(raw)
    except Exception:
        # Fallos de configuración no revelan rutas, JSON privado ni excepciones.
        response = {'protocol': PROTOCOL, 'operation_id': '00000000-0000-0000-0000-000000000000',
            'action': 'inspect', 'resource_uuid': '00000000-0000-0000-0000-000000000000',
            'status': 'failed', 'phase': 'configuration', 'identity_verified': False,
            'observed_at': datetime.now(timezone.utc).isoformat(), 'error': {'code': 'RUNNER_UNAVAILABLE',
                'phase': 'configuration', 'retryable': False, 'message': 'Resultado no confirmado; revisar la operación'}}
    print(canonical(response))


if __name__ == '__main__':
    main()
