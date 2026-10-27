"""BookStack fijado: personalización inicial sin secretos en argv."""
import base64
import hashlib
import io
import ipaddress
import json
from pathlib import Path, PurePosixPath
import re
import tarfile
import urllib.request

if __package__:
    from infra.services.common import GuestError, bind_network, canonical, configure_console, install_tls, main, network_configuration
else:
    from common import GuestError, bind_network, canonical, configure_console, install_tls, main, network_configuration


REVISION = '31d94dd8b98e3334dc01b66bed6d514719a2f85d'
SOURCE_SHA256 = '5b16eae97d3de86a56a9e9ca46fd263713fecb5c4ae32e67c9f22e0667780378'
LOCK_SHA256 = '66ddc7f4a71a8ea761ab9db1b0e978bd8f5b18c70571c789e219123c6a7b8ea6'
DIRECTORY = 'etc/nap/bookstack'
APPLICATION = 'var/www/bookstack'


def extract_application(raw, destination):
    """Solo el archivo de la revisión oficial; sin enlaces ni escapes."""
    if len(raw) > 67108864 or hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
        raise GuestError('ARTIFACT_MISMATCH')
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise GuestError('UNSUPPORTED_GUEST')
    prefix = 'BookStack-' + REVISION
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
        members = archive.getmembers()
        if len(members) > 20000 or sum(item.size for item in members) > 67108864:
            raise GuestError('ARTIFACT_MISMATCH')
        for item in members:
            parts = PurePosixPath(item.name).parts
            if not parts or parts[0] != prefix or '..' in parts or not (item.isdir() or item.isfile()):
                raise GuestError('ARTIFACT_MISMATCH')
        destination.mkdir(parents=True, mode=0o755)
        for item in members:
            item.name = '/'.join(PurePosixPath(item.name).parts[1:])
            if item.name:
                archive.extract(item, path=destination, filter='data')
    if (destination / 'version').read_text().strip() != 'v26.09.1' or hashlib.sha256(
        (destination / 'composer.lock').read_bytes()).hexdigest() != LOCK_SHA256:
        raise GuestError('ARTIFACT_MISMATCH')


def install_application(plan):
    """Solo host de build/chroot. Nunca invocado desde el bootstrap guest."""
    component = plan['manifest']['runtime']['components']['bookstack']
    if component != {'version': '26.09.1', 'revision': REVISION,
        'source_sha256': SOURCE_SHA256, 'composer_lock_sha256': LOCK_SHA256}:
        raise GuestError('ARTIFACT_MISMATCH')
    with urllib.request.urlopen('https://codeload.github.com/BookStackApp/BookStack/tar.gz/' + REVISION, timeout=30) as source:
        raw = source.read(67108865)
    extract_application(raw, '/' + APPLICATION)


def _parameters(request):
    parameters = request.get('parameters', {})
    email = parameters.get('teacher_email', '')
    if (set(parameters) != {'display_name', 'teacher_name', 'teacher_email', 'locale'}
        or parameters['locale'] not in {'es', 'en'} or email.lower() == 'admin@admin.com'
        or len(email) > 254 or not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}", email)):
        raise GuestError('INVALID_REQUEST')
    return parameters


def _key(value):
    try:
        if not value.startswith('base64:') or len(base64.b64decode(value[7:], validate=True)) != 32:
            raise ValueError()
    except (ValueError, TypeError):
        raise GuestError('INVALID_REQUEST') from None
    return value


def _php(context, action):
    # El archivo PHP forma parte del bundle firmado por digest, con ruta fija.
    payload = {'action': action, 'resource_uuid': context.request['resource_uuid'], **_parameters(context.request)}
    if action == 'initialize':
        payload['teacher_password'] = context.request['secrets']['teacher_password']
    response = context.system.run(['/usr/bin/php8.3', str(Path(__file__).with_name('configure.php'))],
        input=canonical(payload), timeout=120)
    try:
        if json.loads(response) != {'ready': True}:
            raise ValueError()
    except (ValueError, TypeError):
        raise GuestError('PROBE_FAILED') from None


def _web_configuration(network):
    address = ipaddress.ip_address(network['address'])
    listen = '[' + str(address) + ']' if address.version == 6 else str(address)
    allowed = ''.join('    allow ' + cidr + ';\n' for cidr in network['client_cidrs'])
    return fr"""server {{
    listen 127.0.0.1:443 ssl;
    listen {listen}:443 ssl;
    server_name {network['host']};
    if ($host != {network['host']}) {{ return 444; }}
    root /var/www/bookstack/public;
    index index.php;
    server_tokens off;
    ssl_certificate /{DIRECTORY}/server.crt;
    ssl_certificate_key /{DIRECTORY}/server.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    allow 127.0.0.1;
{allowed}    deny all;
    client_max_body_size 50m;
    location / {{ try_files $uri $uri/ /index.php?$query_string; }}
    location ^~ /storage/ {{ deny all; }}
    location ^~ /uploads/files/ {{ deny all; }}
    location ^~ /uploads/images/ {{ rewrite ^ /index.php last; }}
    location ~ /\. {{ deny all; }}
    location = /index.php {{
        include fastcgi_params;
        fastcgi_param SCRIPT_FILENAME /var/www/bookstack/public/index.php;
        fastcgi_param HTTPS on;
        fastcgi_pass unix:/run/php/nap-bookstack.sock;
    }}
    location ~ \.php(?:/|$) {{ deny all; }}
}}
"""


class BookStack:
    parameters = ['display_name', 'teacher_name', 'teacher_email', 'locale']
    secret_fields = ['teacher_password', 'database_password', 'app_key']

    def prepare(self, context):
        system = context.system
        parameters = _parameters(context.request)
        network = network_configuration(context.request)
        bind_network(context, network)
        values = context.request['secrets']
        app_key = _key(values['app_key'])
        password = values['database_password']
        if not re.fullmatch(r'[A-Za-z0-9_-]{20,128}', password):
            raise GuestError('INVALID_REQUEST')
        if system.path('var/lib/mysql/mysql').exists() and not context.steps.get('database_directory'):
            raise GuestError('UNSUPPORTED_GUEST')
        if system.path(APPLICATION + '/.env').exists() and not context.steps.get('environment'):
            raise GuestError('UNSUPPORTED_GUEST')
        context.step('tls', lambda: install_tls(system, network, DIRECTORY, owner='root:root'))
        context.step('console_configuration', lambda: configure_console(system))
        def database_directory():
            if system.path('var/lib/mysql/mysql/global_priv.MAD').is_file():
                return
            if system.path('var/lib/mysql').exists() and any(system.path('var/lib/mysql').iterdir()):
                raise GuestError('UNCONFIRMED')
            system.run(['/usr/bin/install', '-d', '-o', 'mysql', '-g', 'mysql', '-m', '0750', '/var/lib/mysql', '/run/mysqld'])
            system.run(['/usr/bin/mariadb-install-db', '--no-defaults', '--user=mysql', '--datadir=/var/lib/mysql',
                '--auth-root-authentication-method=socket', '--skip-test-db'], timeout=120)
        context.step('database_directory', database_directory)
        context.step('mariadb_configuration', lambda: system.write('etc/mysql/mariadb.conf.d/99-nap.cnf',
            '[mysqld]\nskip-networking\nlocal_infile=0\ngeneral_log=0\nslow_query_log=0\n', mode=0o644))
        system.run(['/usr/bin/systemctl', 'unmask', 'mariadb.service'])
        system.run(['/usr/bin/systemctl', 'start', 'mariadb.service'])
        def database():
            verifier = '*' + hashlib.sha1(hashlib.sha1(password.encode()).digest()).hexdigest().upper()
            system.run(['/usr/bin/mariadb', '--no-defaults', '--protocol=socket', '--user=root', '--batch', '--skip-column-names'], input=f"""
CREATE DATABASE IF NOT EXISTS bookstack CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'bookstack'@'localhost' IDENTIFIED BY PASSWORD '{verifier}';
GRANT ALL PRIVILEGES ON bookstack.* TO 'bookstack'@'localhost';
""")
        context.step('database', database)
        def environment():
            fields = {'APP_ENV': 'production', 'APP_DEBUG': 'false', 'APP_URL': 'https://' + network['host'],
                'APP_KEY': app_key, 'APP_LANG': parameters['locale'], 'APP_AUTO_LANG_PUBLIC': 'false',
                'DB_HOST': 'localhost', 'DB_DATABASE': 'bookstack', 'DB_USERNAME': 'bookstack', 'DB_PASSWORD': password,
                'AUTH_METHOD': 'standard', 'STORAGE_TYPE': 'local_secure', 'STORAGE_IMAGE_TYPE': 'local_secure',
                'STORAGE_ATTACHMENT_TYPE': 'local_secure', 'SESSION_DRIVER': 'file', 'SESSION_SECURE_COOKIE': 'true',
                'MAIL_DRIVER': 'log'}
            system.write(APPLICATION + '/.env', ''.join(name + '=' + value + '\n' for name, value in fields.items()), mode=0o640)
            system.run(['/usr/bin/chown', 'root:www-data', '/' + APPLICATION + '/.env'])
            for directory in ['storage/uploads/images', 'storage/uploads/files', 'storage/logs',
                'storage/framework/cache', 'storage/framework/cache/data',
                'storage/framework/sessions', 'storage/framework/views', 'bootstrap/cache', 'public/uploads', 'themes']:
                system.run(['/usr/bin/install', '-d', '-o', 'www-data', '-g', 'www-data', '-m', '0775', '/' + APPLICATION + '/' + directory])
            system.run(['/usr/bin/chown', '-R', 'www-data:www-data', '/' + APPLICATION + '/storage', '/' + APPLICATION + '/bootstrap/cache'])
        context.step('environment', environment)
        artisan = ['/usr/bin/php8.3', '/' + APPLICATION + '/artisan']
        context.step('package_discovery', lambda: system.run(artisan + ['package:discover', '--no-interaction', '--no-ansi']))
        context.step('migrations', lambda: system.run(artisan + ['migrate', '--force', '--no-interaction', '--no-ansi'], timeout=300))
        context.step('teacher_and_settings', lambda: _php(context, 'initialize'))
        def web_configuration():
            system.run(['/usr/bin/install', '-d', '-o', 'root', '-g', 'adm', '-m', '0750', '/var/log/nginx'])
            system.run(['/usr/bin/install', '-d', '-o', 'www-data', '-g', 'www-data', '-m', '0755', '/run/php'])
            system.write('etc/nginx/sites-enabled/nap-bookstack.conf', _web_configuration(network), mode=0o644)
            system.write('etc/php/8.3/fpm/pool.d/nap-bookstack.conf',
                '[nap-bookstack]\nuser = www-data\ngroup = www-data\nlisten = /run/php/nap-bookstack.sock\n'
                'listen.owner = www-data\nlisten.group = www-data\nlisten.mode = 0660\n'
                'pm = dynamic\npm.max_children = 5\npm.start_servers = 1\npm.min_spare_servers = 1\npm.max_spare_servers = 2\n'
                'clear_env = yes\nsecurity.limit_extensions = .php\nphp_admin_flag[display_errors] = off\n'
                'php_admin_flag[expose_php] = off\n', mode=0o644)
            system.run(['/usr/sbin/nginx', '-t'])
            system.run(['/usr/sbin/php-fpm8.3', '--test'])
        context.step('web_configuration', web_configuration)
        _php(context, 'check')
        # Nginx continúa enmascarado hasta sustituir la cuenta inicial y cerrar
        # público/registro. No hay ventana de exposición con credenciales conocidas.
        for service in ['mariadb.service', 'php8.3-fpm.service', 'nginx.service']:
            system.run(['/usr/bin/systemctl', 'unmask', service])
            system.run(['/usr/bin/systemctl', 'enable', service])
            system.run(['/usr/bin/systemctl', 'start', service])

    def inspect(self, context):
        if __package__:
            from infra.services.common import GuestCommandError
        else:
            from common import GuestCommandError
        network = network_configuration(context.request)
        bind_network(context, network)
        parameters = _parameters(context.request)
        base = ['/usr/bin/curl', '--silent', '--show-error', '--fail', '--noproxy', '*', '--max-time', '10',
            '--proto', '=https', '--cacert', '/' + DIRECTORY + '/ca.crt', '--resolve', network['host'] + ':443:127.0.0.1']
        endpoint = 'https://' + network['host']
        stage = 'application'
        try:
            _php(context, 'check')
            stage = 'http'
            status = json.loads(context.system.run(base + [endpoint + '/status'], timeout=15))
            login = context.system.run(base + ['--output', '/dev/null', '--write-out', '%{http_code}', endpoint + '/login'], timeout=15)
            ready = status == {'database': True, 'cache': True, 'session': True} and login == '200'
        except GuestCommandError as exc:
            # PHP check usa 1 para un fallo funcional. curl usa estos códigos
            # para conexión/HTTP/deadline/TLS comprobados desde el propio guest.
            if not (stage == 'application' and exc.returncode == 1
                or stage == 'http' and exc.returncode in {7,22,28,35,60}): raise
            ready = False
        except (ValueError, TypeError):
            ready = False
        return {'ready': ready, 'bootstrap_completed': bool(context.state.get('completed')), 'endpoint': endpoint,
            'host': network['host'], 'address': network['address'], 'port': 443, 'username': parameters['teacher_email'],
            'checks': ['bookstack-status-v1'] if ready else []}

    def verify(self, context):
        result = self.inspect(context)
        if not result['ready']:
            raise GuestError('PROBE_FAILED')
        return result


if __name__ == '__main__':
    main(BookStack())
