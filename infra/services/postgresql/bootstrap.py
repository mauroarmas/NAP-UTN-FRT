"""PostgreSQL 16: clúster nuevo, rol de instancia y probes autenticados."""
import base64
import hashlib
import hmac
import ipaddress
import secrets
from uuid import UUID

if __package__:
    from infra.services.common import GuestError, bind_network, configure_console, install_tls, main, network_configuration
else:
    from common import GuestError, bind_network, configure_console, install_tls, main, network_configuration


DIRECTORY = 'etc/nap/postgresql'
PRIVILEGES = 'NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT'


def scram_verifier(password, *, salt=None):
    # Los secretos de instancia son ASCII aleatorio. No aceptar Unicode que
    # libpq pueda normalizar de forma diferente mediante SASLprep.
    if not isinstance(password, str) or not password.isascii():
        raise GuestError('INVALID_REQUEST')
    salt = salt or secrets.token_bytes(16)
    salted = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 4096)
    stored = hashlib.sha256(hmac.digest(salted, b'Client Key', 'sha256')).digest()
    server = hmac.digest(salted, b'Server Key', 'sha256')
    encoded = lambda item: base64.b64encode(item).decode()
    return 'SCRAM-SHA-256$4096:' + encoded(salt) + '$' + encoded(stored) + ':' + encoded(server)


def _names(context):
    suffix = UUID(context.request['resource_uuid']).hex
    return context.request.get('parameters', {}).get('database_name', 'curso_' + suffix), 'curso_' + suffix


def _psql(system, database, sql, *, user='postgres', network=None, passfile=None):
    env = {'PGCONNECT_TIMEOUT': '5', 'PGOPTIONS': '-c statement_timeout=10000 -c lock_timeout=5000'}
    if network is None:
        argv = ['/usr/sbin/runuser', '--user', 'postgres', '--', '/usr/bin/psql']
        env.update({'PGHOST': '/var/run/postgresql', 'PGPORT': '5432'})
    else:
        argv = ['/usr/bin/psql']
        env.update({'PGHOST': network['host'], 'PGHOSTADDR': '127.0.0.1', 'PGPORT': '5432',
            'PGSSLMODE': 'verify-full', 'PGSSLROOTCERT': '/' + DIRECTORY + '/ca.crt', 'PGPASSFILE': '/' + passfile})
    argv += ['--no-psqlrc', '--no-password', '--quiet', '--tuples-only', '--no-align',
        '--set', 'ON_ERROR_STOP=1', '--username', user, '--dbname', database]
    return system.run(argv, input=sql, timeout=20, env=env).strip()


def _passfile(system, name, network, database, user, password):
    escape = lambda text: text.replace('\\', '\\\\').replace(':', '\\:')
    system.write(DIRECTORY + '/' + name, ':'.join(map(escape, [network['host'], '5432', database, user, password])) + '\n')
    return DIRECTORY + '/' + name


def _identity_probe(context):
    database, owner = _names(context)
    result = _psql(context.system, 'postgres', f"""/* NAP_IDENTITY */
SELECT current_setting('server_version_num')::int / 10000 || '|' ||
CASE WHEN EXISTS (SELECT 1 FROM pg_database d JOIN pg_roles r ON r.oid=d.datdba
 WHERE d.datname='{database}' AND r.rolname='{owner}' AND r.rolcanlogin
 AND NOT (r.rolsuper OR r.rolcreatedb OR r.rolcreaterole OR r.rolreplication OR r.rolbypassrls)
 AND NOT EXISTS (SELECT 1 FROM pg_auth_members m WHERE m.member=r.oid))
THEN 'safe' ELSE 'unsafe' END;
""")
    if result != '16|safe':
        raise GuestError('PROBE_FAILED')


class PostgreSQL:
    parameters = ['display_name', 'database_name']
    secret_fields = ['database_password']

    def prepare(self, context):
        system = context.system
        network = network_configuration(context.request)
        bind_network(context, network)
        # TLS inválido falla antes de crear datos nuevos.
        context.step('tls', lambda: install_tls(system, network, DIRECTORY, owner='postgres:postgres'))
        version = system.read('var/lib/postgresql/16/main/PG_VERSION').strip()
        if version and not context.steps.get('cluster'):
            raise GuestError('UNSUPPORTED_GUEST')
        database, owner = _names(context)
        password = context.request['secrets']['database_password']
        owner_verifier = scram_verifier(password)
        context.step('console_configuration', lambda: configure_console(system))
        def cluster():
            if system.read('var/lib/postgresql/16/main/PG_VERSION').strip() == '16':
                if not system.read('etc/postgresql/16/main/postgresql.conf'):
                    raise GuestError('UNCONFIRMED')
                return
            if system.path('var/lib/postgresql/16/main').exists() or system.path('etc/postgresql/16/main').exists():
                raise GuestError('UNCONFIRMED')
            system.run(['/usr/bin/install', '-d', '-o', 'postgres', '-g', 'postgres', '-m', '0750',
                '/var/log/postgresql', '/var/lib/postgresql', '/run/postgresql'])
            system.run(['/usr/bin/pg_createcluster', '--start-conf=manual', '--locale=C.UTF-8', '--port=5432',
                '16', 'main', '--', '--auth-local=peer', '--auth-host=scram-sha-256'], timeout=120)
        context.step('cluster', cluster)
        def configuration():
            address = ipaddress.ip_address(network['address'])
            clients = list(dict.fromkeys(['127.0.0.1/32', *network['client_cidrs']]))
            hba = ['local all postgres peer', 'hostssl nap_health nap_health 127.0.0.1/32 scram-sha-256']
            hba += [f'hostssl {database} {owner} {cidr} scram-sha-256' for cidr in clients]
            hba += ['host all all 0.0.0.0/0 reject', 'host all all ::/0 reject']
            system.write('etc/postgresql/16/main/pg_hba.conf', '\n'.join(hba) + '\n', mode=0o640)
            system.write('etc/postgresql/16/main/conf.d/nap.conf',
                f"listen_addresses = '127.0.0.1,{address}'\nport = 5432\nssl = on\n"
                "ssl_min_protocol_version = 'TLSv1.2'\npassword_encryption = 'scram-sha-256'\n"
                f"ssl_cert_file = '/{DIRECTORY}/server.crt'\nssl_key_file = '/{DIRECTORY}/server.key'\n"
                "log_statement = 'none'\nlog_min_error_statement = 'panic'\nlog_parameter_max_length_on_error = 0\n", mode=0o640)
            system.run(['/usr/bin/chown', 'postgres:postgres', '/etc/postgresql/16/main/pg_hba.conf',
                '/etc/postgresql/16/main/conf.d/nap.conf'])
        context.step('configuration', configuration)
        system.run(['/usr/bin/systemctl', 'unmask', 'postgresql@16-main.service'])
        system.run(['/usr/bin/systemctl', 'start', 'postgresql@16-main.service'])
        monitor_file = DIRECTORY + '/monitor.secret'
        if not system.read(monitor_file):
            if context.steps.get('roles'):
                raise GuestError('UNCONFIRMED')
            system.write(monitor_file, secrets.token_urlsafe(32))
        monitor = system.read(monitor_file)
        system.forbidden_arguments.add(monitor)
        monitor_verifier = scram_verifier(monitor)
        def roles():
            _psql(system, 'postgres', f"""DO $nap$ BEGIN
IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='{owner}') THEN
 CREATE ROLE {owner} LOGIN {PRIVILEGES} PASSWORD '{owner_verifier}';
END IF;
IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='nap_health') THEN
 CREATE ROLE nap_health LOGIN {PRIVILEGES} PASSWORD '{monitor_verifier}';
END IF;
END $nap$;
SELECT 'CREATE DATABASE {database} OWNER {owner}' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname='{database}')\n\\gexec
SELECT 'CREATE DATABASE nap_health OWNER postgres' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname='nap_health')\n\\gexec
REVOKE CONNECT, TEMPORARY ON DATABASE {database} FROM PUBLIC;
REVOKE CONNECT, TEMPORARY ON DATABASE postgres FROM PUBLIC;
REVOKE CONNECT, TEMPORARY ON DATABASE template1 FROM PUBLIC;
REVOKE CONNECT, TEMPORARY ON DATABASE nap_health FROM PUBLIC;
GRANT CONNECT ON DATABASE nap_health TO nap_health;
""")
            _identity_probe(context)
        context.step('roles', roles)
        _passfile(system, 'monitor.pgpass', network, 'nap_health', 'nap_health', monitor)
        def write_probe():
            path = _passfile(system, 'owner.pgpass', network, database, owner, password)
            try:
                result = _psql(system, database, """/* NAP_WRITE_PROBE */
BEGIN;
CREATE TEMPORARY TABLE nap_probe(value text) ON COMMIT DROP;
INSERT INTO nap_probe VALUES ('nap-probe-ok');
SELECT value FROM nap_probe;
ROLLBACK;
""", user=owner, network=network, passfile=path)
                if result != 'nap-probe-ok':
                    raise GuestError('PROBE_FAILED')
            finally:
                system.path(path).unlink(missing_ok=True)
        context.step('write_probe', write_probe)
        def auto_start():
            system.write('etc/postgresql/16/main/start.conf', 'auto\n', mode=0o644)
            system.run(['/usr/bin/systemctl', 'unmask', 'postgresql.service'])
            system.run(['/usr/bin/systemctl', 'enable', 'postgresql.service'])
            system.run(['/usr/bin/systemctl', 'daemon-reload'])
        context.step('auto_start', auto_start)

    def inspect(self, context):
        if __package__:
            from infra.services.common import GuestCommandError
        else:
            from common import GuestCommandError
        network = network_configuration(context.request)
        bind_network(context, network)
        database, owner = _names(context)
        try:
            probe = _psql(context.system, 'nap_health', '/* NAP_HEALTH */ SELECT 1;', user='nap_health',
                network=network, passfile=DIRECTORY + '/monitor.pgpass')
        except GuestCommandError as exc:
            # psql confirmó fallo de conexión/consulta al destino local; un
            # fallo al iniciar el proceso o perder SSH sigue siendo desconocido.
            if exc.returncode not in {2,3}: raise
            probe = None
        return {'ready': probe == '1' and context.system.read('var/lib/postgresql/16/main/PG_VERSION').strip() == '16',
            'bootstrap_completed': bool(context.state.get('completed')), 'database': database, 'username': owner,
            'host': network['host'], 'address': network['address'], 'port': 5432,
            'checks': ['postgresql-select-v1']}

    def verify(self, context):
        _identity_probe(context)
        result = self.inspect(context)
        if not result['ready']:
            raise GuestError('PROBE_FAILED')
        return result


if __name__ == '__main__':
    main(PostgreSQL())
