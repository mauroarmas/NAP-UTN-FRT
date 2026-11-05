"""Receta BookStack sin procesos, red ni base de aplicación reales."""
import base64
import json
from uuid import uuid4

import pytest

from tests.test_guest_runner_client import request


def book_request():
    return request() | {
        'parameters': {'display_name': 'Libro de la cátedra', 'teacher_name': 'Ana Pérez',
            'teacher_email': 'ana@example.edu', 'locale': 'es'},
        'secrets': {'teacher_password': 'teacher-private-password-001',
            'database_password': 'database-private-password-001',
            'app_key': 'base64:' + base64.b64encode(bytes(range(32))).decode()},
        'infrastructure': {'host': 'libro.example.edu', 'address': '10.50.0.102',
            'client_cidrs': ['10.50.0.0/24'], 'tls_certificate': 'CERTIFICATE-test-only',
            'tls_private_key': 'PRIVATE-KEY-test-only', 'tls_ca': 'CA-CERTIFICATE-test-only'},
    }


@pytest.fixture
def book_system(tmp_path):
    from infra.services.common import GuestSystem
    class System(GuestSystem):
        def __init__(self):
            super().__init__(root=tmp_path)
            self.commands, self.sql, self.php_inputs = [], [], []
            self.initializations = 0
            self.healthy = True
        def run(self, argv, *, input=None, **kwargs):
            assert not any(secret in str(arg) for secret in self.forbidden_arguments for arg in argv)
            self.commands.append(list(argv))
            if argv[0] == '/usr/bin/mariadb-install-db':
                self.initializations += 1
                self.write('var/lib/mysql/mysql/global_priv.MAD', 'new-system-tables')
            if argv[0] == '/usr/bin/mariadb':
                self.sql.append(input)
            if argv[0] == '/usr/bin/php8.3' and argv[-1].endswith('configure.php'):
                self.php_inputs.append(json.loads(input))
                return '{"ready":true}\n'
            if argv[:2] == ['/usr/bin/openssl', 'x509'] and '-pubkey' in argv:
                return 'PUBLIC-KEY\n'
            if argv[:2] == ['/usr/bin/openssl', 'pkey']:
                return 'PUBLIC-KEY\n'
            if argv[0] == '/usr/bin/curl':
                if argv[-1].endswith('/status'):
                    return json.dumps({'database': self.healthy, 'cache': True, 'session': True})
                return '200' if self.healthy else '503'
            return ''
    return System()


def test_bookstack_is_private_and_has_instance_key_and_local_teacher_admin(book_system):
    from infra.services.common import run_product
    from infra.services.bookstack.bootstrap import BookStack
    value = book_request()
    result = run_product(BookStack(), value, system=book_system)
    assert result['ready'] and result['endpoint'] == 'https://libro.example.edu'
    assert result['username'] == 'ana@example.edu' and book_system.initializations == 1
    env = book_system.read('var/www/bookstack/.env')
    for line in ['APP_URL=https://libro.example.edu', 'STORAGE_TYPE=local_secure',
        'STORAGE_IMAGE_TYPE=local_secure', 'STORAGE_ATTACHMENT_TYPE=local_secure',
        'APP_DEBUG=false', 'SESSION_SECURE_COOKIE=true', 'DB_HOST=localhost']:
        assert line in env
    assert value['secrets']['app_key'] in env
    assert value['secrets']['teacher_password'] not in env
    assert book_system.path('var/www/bookstack/.env').stat().st_mode & 0o777 == 0o640
    nginx = book_system.read('etc/nginx/sites-enabled/nap-bookstack.conf')
    assert 'ssl_protocols TLSv1.2 TLSv1.3' in nginx and 'deny all' in nginx
    assert 'root /var/www/bookstack/public' in nginx and 'fastcgi_pass unix:/run/php/nap-bookstack.sock' in nginx
    assert '/storage/' in nginx and '10.50.0.0/24' in nginx
    initialize = next(x for x in book_system.php_inputs if x['action'] == 'initialize')
    assert initialize['teacher_password'] == value['secrets']['teacher_password']
    assert 'skip-networking' in book_system.read('etc/mysql/mariadb.conf.d/99-nap.cnf')
    sql = '\n'.join(book_system.sql)
    assert 'ON bookstack.*' in sql and 'GRANT OPTION' not in sql
    metadata = book_system.read('var/lib/nap/bootstrap.json')
    for secret in [*value['secrets'].values(), value['nonce'], value['infrastructure']['tls_private_key']]:
        assert secret not in metadata + json.dumps(result) + repr(book_system.commands) + sql


def test_bookstack_retry_never_regenerates_app_key_or_changes_password(book_system):
    from infra.services.common import run_product, GuestError
    from infra.services.bookstack.bootstrap import BookStack
    value = book_request()
    run_product(BookStack(), value, system=book_system)
    env_before = book_system.read('var/www/bookstack/.env')
    commands_before = len(book_system.commands)
    run_product(BookStack(), value | {'operation_id': str(uuid4())}, system=book_system)
    assert book_system.initializations == 1
    assert len([x for x in book_system.php_inputs if x['action'] == 'initialize']) == 1
    assert book_system.read('var/www/bookstack/.env') == env_before
    assert not any('migrate' in command for command in book_system.commands[commands_before:])
    with pytest.raises(GuestError) as exc:
        run_product(BookStack(), value | {'secrets': value['secrets'] | {'app_key': 'base64:' + base64.b64encode(b'x' * 32).decode()}}, system=book_system)
    assert exc.value.code == 'IDEMPOTENCY_CONFLICT'


@pytest.mark.parametrize('parameters', [
    {'teacher_email': 'admin@admin.com'}, {'teacher_email': 'bad email'},
    {'locale': 'arbitrary'}, {'teacher_name': ''},
])
def test_invalid_teacher_details_fail_before_database_creation(book_system, parameters):
    from infra.services.common import run_product, GuestError
    from infra.services.bookstack.bootstrap import BookStack
    value = book_request(); value['parameters'].update(parameters)
    with pytest.raises(GuestError):
        run_product(BookStack(), value, system=book_system)
    assert book_system.initializations == 0


def test_invalid_app_key_and_existing_data_are_never_replaced(book_system):
    from infra.services.common import run_product, GuestError
    from infra.services.bookstack.bootstrap import BookStack
    value = book_request()
    with pytest.raises(GuestError):
        run_product(BookStack(), value | {'secrets': value['secrets'] | {'app_key': 'not-a-valid-base64-256-bit-key'}}, system=book_system)
    assert book_system.initializations == 0
    # Otra identidad para no confundir la huella rechazada con datos anteriores.
    book_system.root = book_system.root / 'other'; book_system.root.mkdir()
    book_system.write('var/lib/mysql/mysql/global_priv.MAD', 'preexisting')
    with pytest.raises(GuestError) as exc:
        run_product(BookStack(), value, system=book_system)
    assert exc.value.code == 'UNSUPPORTED_GUEST'
    assert book_system.initializations == 0 and not book_system.sql


def test_bookstack_status_is_not_healthy_just_because_http_is_200(book_system):
    from infra.services.common import run_product, GuestError
    from infra.services.bookstack.bootstrap import BookStack
    book_system.healthy = False
    with pytest.raises(GuestError):
        run_product(BookStack(), book_request(), system=book_system)
    assert not json.loads(book_system.read('var/lib/nap/bootstrap.json'))['completed']


def test_bookstack_read_probe_needs_no_key_and_rejects_changed_network(book_system):
    from infra.services.common import run_product, GuestError
    from infra.services.bookstack.bootstrap import BookStack
    value = book_request()
    run_product(BookStack(), value, system=book_system)
    inspection = {k: v for k, v in (value | {'action': 'verify'}).items() if k != 'secrets'}
    inspection['infrastructure'] = {k: v for k, v in value['infrastructure'].items() if not k.startswith('tls_')}
    assert run_product(BookStack(), inspection, system=book_system)['ready']
    inspection['infrastructure']['client_cidrs'] = ['10.60.0.0/24']
    with pytest.raises(GuestError) as exc:
        run_product(BookStack(), inspection, system=book_system)
    assert exc.value.code == 'IDENTITY_MISMATCH'


def test_http_failure_is_negative_after_verified_bootstrap_but_collection_failure_is_unknown(book_system, monkeypatch):
    from infra.services.common import run_product, GuestCommandError, GuestError
    from infra.services.bookstack.bootstrap import BookStack
    value = book_request()
    run_product(BookStack(), value, system=book_system)
    reading = {k:v for k,v in (value | {'action':'inspect'}).items() if k != 'secrets'}
    reading['infrastructure'] = {k:v for k,v in value['infrastructure'].items() if not k.startswith('tls_')}
    original = book_system.run
    def failed(argv, **kwargs):
        if argv[0] == '/usr/bin/curl': raise GuestCommandError(22)
        return original(argv, **kwargs)
    monkeypatch.setattr(book_system, 'run', failed)
    result = run_product(BookStack(), reading, system=book_system)
    assert result['ready'] is False and result['bootstrap_completed'] is True
    assert result['host'] == 'libro.example.edu'
    def unavailable(argv, **kwargs):
        if argv[0] == '/usr/bin/curl': raise GuestError('BOOTSTRAP_FAILED')
        return original(argv, **kwargs)
    monkeypatch.setattr(book_system, 'run', unavailable)
    with pytest.raises(GuestError):
        run_product(BookStack(), reading, system=book_system)
    def invalid_command(argv, **kwargs):
        if argv[0] == '/usr/bin/curl': raise GuestCommandError(1)
        return original(argv, **kwargs)
    monkeypatch.setattr(book_system, 'run', invalid_command)
    with pytest.raises(GuestCommandError):
        run_product(BookStack(), reading, system=book_system)


def test_guest_command_failure_keeps_only_exit_code_without_raw_subprocess_values(book_system, monkeypatch, caplog):
    import subprocess
    from infra.services.common import GuestSystem, GuestCommandError
    def fail(argv, **kwargs):
        raise subprocess.CalledProcessError(22, argv, output='private-stdout-value', stderr='private-stderr-value')
    monkeypatch.setattr(subprocess, 'run', fail)
    with pytest.raises(GuestCommandError) as caught:
        GuestSystem(root=book_system.root).run(['/usr/bin/curl', 'https://example.invalid'])
    assert caught.value.returncode == 22 and str(caught.value) == 'BOOTSTRAP_FAILED'
    assert set(vars(caught.value)) == {'code','returncode'}
    assert 'private-stdout-value' not in caplog.text and 'private-stderr-value' not in caplog.text
