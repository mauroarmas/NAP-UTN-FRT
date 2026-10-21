"""Contrato de la receta; dobles sin PostgreSQL, red o chroot reales."""
import base64
import hashlib
import hmac
import json
from uuid import uuid4

import pytest

from tests.test_guest_runner_client import request


def pg_request():
    return request() | {
        'parameters': {'display_name': 'Base del curso', 'database_name': 'curso'},
        'secrets': {'database_password': 'instance-private-password-001'},
        # Material inyectado por infraestructura, nunca por el solicitante.
        'infrastructure': {'host': 'curso.example.edu', 'address': '10.50.0.101',
            'client_cidrs': ['10.50.0.0/24'], 'tls_certificate': 'CERTIFICATE-test-only',
            'tls_private_key': 'PRIVATE-KEY-test-only', 'tls_ca': 'CA-CERTIFICATE-test-only'},
    }


@pytest.fixture
def pg_system(tmp_path):
    from infra.services.common import GuestSystem
    class System(GuestSystem):
        def __init__(self):
            super().__init__(root=tmp_path)
            self.commands, self.sql, self.environments = [], [], []
            self.initializations = 0
            self.fail_probe = False
        def run(self, argv, *, input=None, env=None, **kwargs):
            assert not any(secret in str(arg) for secret in self.forbidden_arguments for arg in argv)
            self.commands.append(list(argv)); self.environments.append(env or {})
            if argv[0] == '/usr/bin/pg_createcluster':
                self.initializations += 1
                self.write('var/lib/postgresql/16/main/PG_VERSION', '16\n')
                self.write('etc/postgresql/16/main/postgresql.conf', '# paquete\n')
                self.write('etc/postgresql/16/main/pg_hba.conf', '# paquete\n')
            if '/usr/bin/psql' in argv:
                self.sql.append(input)
                if 'NAP_WRITE_PROBE' in input:
                    if self.fail_probe:
                        return '0\n'
                    return 'nap-probe-ok\n'
                if 'NAP_HEALTH' in input:
                    return '1\n' if not self.fail_probe else '0\n'
                if 'NAP_IDENTITY' in input:
                    return '16|safe\n'
            if argv[:2] == ['/usr/bin/openssl', 'x509'] and '-pubkey' in argv:
                return 'PUBLIC-KEY\n'
            if argv[:2] == ['/usr/bin/openssl', 'pkey']:
                return 'PUBLIC-KEY\n'
            return ''
    return System()


def test_postgresql_fresh_cluster_restricted_roles_tls_and_rolled_back_probe(pg_system):
    from infra.services.common import run_product
    from infra.services.postgresql.bootstrap import PostgreSQL
    value = pg_request()
    result = run_product(PostgreSQL(), value, system=pg_system)
    assert result['ready'] and result['database'] == 'curso'
    assert result['host'] == 'curso.example.edu' and result['port'] == 5432
    assert pg_system.initializations == 1
    sql = '\n'.join(pg_system.sql)
    for permission in ['NOSUPERUSER', 'NOCREATEDB', 'NOCREATEROLE', 'NOREPLICATION', 'NOBYPASSRLS']:
        assert permission in sql
    assert 'SCRAM-SHA-256$' in sql and 'ROLLBACK' in sql and 'NAP_WRITE_PROBE' in sql
    assert value['secrets']['database_password'] not in sql
    hba = pg_system.read('etc/postgresql/16/main/pg_hba.conf')
    assert 'hostssl' in hba and 'scram-sha-256' in hba and '10.50.0.0/24' in hba
    assert 'trust' not in hba and '0.0.0.0/0 scram-sha-256' not in hba
    config = pg_system.read('etc/postgresql/16/main/conf.d/nap.conf')
    assert "ssl = on" in config and "ssl_min_protocol_version = 'TLSv1.2'" in config
    assert 'verify-full' in repr(pg_system.environments)
    assert 'PGPASSWORD' not in repr(pg_system.environments)
    metadata = pg_system.read('var/lib/nap/bootstrap.json')
    for secret in [*value['secrets'].values(), value['nonce'], value['infrastructure']['tls_private_key']]:
        assert secret not in metadata + json.dumps(result) + repr(pg_system.commands)
    assert not pg_system.path('etc/nap/postgresql/owner.pgpass').exists()


def test_postgresql_retry_and_inspect_preserve_database_and_owner_password(pg_system):
    from infra.services.common import run_product, GuestError
    from infra.services.postgresql.bootstrap import PostgreSQL
    value = pg_request()
    run_product(PostgreSQL(), value, system=pg_system)
    writes = len(pg_system.sql)
    run_product(PostgreSQL(), value | {'operation_id': str(uuid4())}, system=pg_system)
    verification = {k: v for k, v in (value | {'action': 'verify'}).items() if k != 'secrets'}
    verification['infrastructure'] = {k: v for k, v in value['infrastructure'].items() if not k.startswith('tls_')}
    inspected = run_product(PostgreSQL(), verification, system=pg_system)
    assert inspected['ready'] and pg_system.initializations == 1
    assert all('CREATE ROLE' not in sql and 'NAP_WRITE_PROBE' not in sql for sql in pg_system.sql[writes:])
    with pytest.raises(GuestError) as exc:
        run_product(PostgreSQL(), value | {'secrets': {'database_password': 'different-instance-password'}}, system=pg_system)
    assert exc.value.code == 'IDEMPOTENCY_CONFLICT'


def test_confirmed_local_connection_failure_is_negative_but_collector_failure_is_unknown(pg_system, monkeypatch):
    from infra.services.common import run_product, GuestCommandError, GuestError
    from infra.services.postgresql.bootstrap import PostgreSQL
    value = pg_request()
    run_product(PostgreSQL(), value, system=pg_system)
    reading = {k:v for k,v in (value | {'action':'inspect'}).items() if k != 'secrets'}
    reading['infrastructure'] = {k:v for k,v in value['infrastructure'].items() if not k.startswith('tls_')}
    original = pg_system.run
    def failed(argv, **kwargs):
        if 'NAP_HEALTH' in (kwargs.get('input') or ''): raise GuestCommandError(2)
        return original(argv, **kwargs)
    monkeypatch.setattr(pg_system, 'run', failed)
    result = run_product(PostgreSQL(), reading, system=pg_system)
    assert result['ready'] is False and result['bootstrap_completed'] is True
    def unavailable(argv, **kwargs):
        raise GuestError('BOOTSTRAP_FAILED')
    monkeypatch.setattr(pg_system, 'run', unavailable)
    with pytest.raises(GuestError):
        run_product(PostgreSQL(), reading, system=pg_system)


def test_postgresql_never_adopts_an_unmarked_database(pg_system):
    from infra.services.common import run_product, GuestError
    from infra.services.postgresql.bootstrap import PostgreSQL
    pg_system.write('var/lib/postgresql/16/main/PG_VERSION', '16\n')
    with pytest.raises(GuestError) as exc:
        run_product(PostgreSQL(), pg_request(), system=pg_system)
    assert exc.value.code == 'UNSUPPORTED_GUEST'
    assert pg_system.initializations == 0 and not pg_system.sql


@pytest.mark.parametrize('change', [
    {'client_cidrs': ['0.0.0.0/0']}, {'address': '127.0.0.1'},
    {'host': 'x\nssl = off'}, {'tls_private_key': ''},
])
def test_invalid_institutional_network_fails_before_initializing(pg_system, change):
    from infra.services.common import run_product, GuestError
    from infra.services.postgresql.bootstrap import PostgreSQL
    value = pg_request()
    value['infrastructure'].update(change)
    with pytest.raises(GuestError):
        run_product(PostgreSQL(), value, system=pg_system)
    assert pg_system.initializations == 0


def test_failed_write_probe_does_not_mark_bootstrap_completed(pg_system):
    from infra.services.common import run_product, GuestError
    from infra.services.postgresql.bootstrap import PostgreSQL
    pg_system.fail_probe = True
    with pytest.raises(GuestError):
        run_product(PostgreSQL(), pg_request(), system=pg_system)
    assert json.loads(pg_system.read('var/lib/nap/bootstrap.json'))['completed'] is False
    assert not pg_system.path('etc/nap/postgresql/owner.pgpass').exists()


def test_postgresql_read_probe_has_no_tls_key_and_rejects_changed_endpoint(pg_system):
    from infra.services.common import run_product, GuestError
    from infra.services.postgresql.bootstrap import PostgreSQL
    value = pg_request()
    run_product(PostgreSQL(), value, system=pg_system)
    inspection = {k: v for k, v in (value | {'action': 'inspect'}).items() if k != 'secrets'}
    inspection['infrastructure'] = {k: v for k, v in value['infrastructure'].items() if not k.startswith('tls_')}
    assert run_product(PostgreSQL(), inspection, system=pg_system)['ready']
    inspection['infrastructure']['host'] = 'another.example.edu'
    with pytest.raises(GuestError) as exc:
        run_product(PostgreSQL(), inspection, system=pg_system)
    assert exc.value.code == 'IDENTITY_MISMATCH'


def test_scram_verifier_matches_sha256_key_derivation():
    from infra.services.postgresql.bootstrap import scram_verifier
    verifier = scram_verifier('a-very-long-ascii-password', salt=b'0123456789abcdef')
    mechanism, parameters, keys = verifier.split('$')
    iterations, salt = parameters.split(':')
    stored, server = map(base64.b64decode, keys.split(':'))
    salted = hashlib.pbkdf2_hmac('sha256', b'a-very-long-ascii-password', base64.b64decode(salt), int(iterations))
    assert mechanism == 'SCRAM-SHA-256' and int(iterations) >= 4096
    assert stored == hashlib.sha256(hmac.digest(salted, b'Client Key', 'sha256')).digest()
    assert server == hmac.digest(salted, b'Server Key', 'sha256')
