#!/usr/bin/env python3
"""Entorno local y copia privada de PostgreSQL; nunca imprime secretos."""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import re
import stat

ROOT = Path(__file__).resolve().parents[1]


def run(args, **kwargs):
    return subprocess.run(args, check=True, stderr=subprocess.PIPE, **kwargs)


def private_write(path, data):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'wb') as handle:
        handle.write(data)


def validate_keyring(value):
    if set(value) != {'secret_keyring', 'secret_active_key'}:
        raise ValueError('Formato de keyring inválido')
    keys = value['secret_keyring']
    if not isinstance(keys, dict) or value['secret_active_key'] not in keys:
        raise ValueError('Keyring incompleto')
    for key in keys.values():
        if len(base64.b64decode(key, altchars=b'-_', validate=True)) != 32:
            raise ValueError('Clave Fernet inválida')
    if any(not re.fullmatch(r'[A-Za-z0-9_-]{1,40}', name) for name in keys):
        raise ValueError('Identificador de clave inválido')
    return value


def read_keyring(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077 or info.st_size > 1048576:
            raise ValueError('Revisar propietario y permisos privados del keyring')
        return validate_keyring(json.load(handle))


def init_env(keyring_path=None):
    if keyring_path:
        keyring = read_keyring(keyring_path)
    else:
        keyring = {'secret_active_key': 'local-v1', 'secret_keyring': {
            'local-v1': base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()}}
    template = (ROOT / '.env.example').read_text()
    template = template.replace('GENERAR_SECRET_KEYRING', json.dumps(keyring['secret_keyring'], separators=(',', ':')))
    template = template.replace('GENERAR_SECRET_KEY', secrets.token_urlsafe(48))
    template = template.replace('GENERAR_CSRF_SECRET', secrets.token_urlsafe(48))
    template = template.replace('SECRET_ACTIVE_KEY=local-v1', 'SECRET_ACTIVE_KEY=' + keyring['secret_active_key'])
    private_write(ROOT / '.env', template.encode())
    print('.env creado con claves propias; no se sobrescriben archivos existentes.')


def digest(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def sql(container, statement, user='postgres', database='postgres'):
    return run(['docker', 'exec', container, 'psql', '-X', '-v', 'ON_ERROR_STOP=1',
                '-U', user, '-d', database, '-Atc', statement], stdout=subprocess.PIPE).stdout.decode().strip()


def inventory(container, user='postgres', database='postgres'):
    tables = sql(container, "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename", user, database).splitlines()
    counts = {table: int(sql(container, 'SELECT count(*) FROM public."' + table.replace('"', '""') + '"', user, database))
              for table in tables}
    revision = sql(container, 'SELECT version_num FROM alembic_version ORDER BY version_num', user, database).splitlines()
    return {'alembic_revisions': revision, 'table_counts': counts}


def restored_inventory(directory):
    """Restauración real en PostgreSQL sin red, puertos ni volumen persistente."""
    name = 'nap-handoff-verify-' + secrets.token_hex(6)
    started = False
    try:
        run(['docker', 'run', '-d', '--name', name, '--network', 'none',
             '--tmpfs', '/var/lib/postgresql/data', '-e', 'POSTGRES_HOST_AUTH_METHOD=trust',
             'postgres:16-alpine'], stdout=subprocess.PIPE)
        started = True
        import time
        for _ in range(60):
            logs = run(['docker', 'logs', name], stdout=subprocess.PIPE)
            result = subprocess.run(['docker', 'exec', name, 'pg_isready', '-U', 'postgres'],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if b'PostgreSQL init process complete' in logs.stdout and result.returncode == 0:
                break
            time.sleep(0.5)
        else:
            raise ValueError('PostgreSQL de verificación no inició')
        with (directory / 'portal.dump').open('rb') as source:
            run(['docker', 'exec', '-i', name, 'pg_restore', '--exit-on-error', '--single-transaction',
                 '--no-owner', '--no-privileges', '-U', 'postgres', '-d', 'postgres'],
                stdin=source, stdout=subprocess.PIPE)
        return inventory(name)
    finally:
        if started:
            run(['docker', 'rm', '-f', name], stdout=subprocess.PIPE)


def export(directory, db_container, api_container):
    directory = directory.expanduser().resolve()
    if directory == ROOT or ROOT in directory.parents:
        raise ValueError('Guardar la copia fuera del repositorio')
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    code = ('import json;from app.config import get_settings;s=get_settings();'
            'print(json.dumps({"secret_keyring":s.secret_keyring,"secret_active_key":s.secret_active_key}))')
    result = run(['docker', 'exec', api_container, 'python', '-c', code], stdout=subprocess.PIPE)
    keys = validate_keyring(json.loads(result.stdout))
    private_write(directory / 'keyring.json', json.dumps(keys).encode())
    # pg_dump mantiene su propia instantánea consistente; no detiene el portal.
    descriptor = os.open(directory / 'portal.dump', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'wb') as output:
        run(['docker', 'exec', db_container, 'pg_dump', '-U', 'ps_user', '-d', 'ps_db',
             '--format=custom', '--no-owner', '--no-privileges'], stdout=output)
    inventory = restored_inventory(directory)
    manifest = {'format': 1, 'created_at_utc': datetime.now(timezone.utc).isoformat(),
                'git_commit': run(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], stdout=subprocess.PIPE).stdout.decode().strip(),
                'postgres_major': 16, **inventory,
                'sha256': {name: digest(directory / name) for name in ('portal.dump', 'keyring.json')},
                'scope': 'Esquema y datos completos del portal; no incluye discos LXC, artefactos ni configuración de infraestructura.'}
    private_write(directory / 'manifest.json', json.dumps(manifest, indent=2).encode())
    print('Copia privada creada y restauración aislada verificada:', directory)
    print('Tablas:', len(inventory['table_counts']), '| Alembic:', ', '.join(inventory['alembic_revisions']))


def verify(directory):
    manifest = json.loads((directory / 'manifest.json').read_bytes())
    if manifest['format'] != 1 or set(manifest['sha256']) != {'portal.dump', 'keyring.json'}:
        raise ValueError('Manifiesto inválido')
    for name, expected in manifest['sha256'].items():
        if digest(directory / name) != expected:
            raise ValueError('Integridad de copia no confirmada')
    read_keyring(directory / 'keyring.json')
    inventory = restored_inventory(directory)
    if any(inventory[key] != manifest[key] for key in ('alembic_revisions', 'table_counts')):
        raise ValueError('Restauración no coincide con el inventario')
    print('Integridad, restauración PostgreSQL, revisión y recuentos verificados.')


def restore(directory, container):
    # Sólo el proyecto de traspaso, con API detenida y base vacía. Nunca --clean.
    details = json.loads(run(['docker', 'inspect', container], stdout=subprocess.PIPE).stdout)[0]
    labels = details['Config'].get('Labels') or {}
    if labels.get('com.docker.compose.project') != 'nap-handoff' or labels.get('com.docker.compose.service') != 'db':
        raise ValueError('Destino fuera del proyecto nap-handoff')
    running = run(['docker', 'ps', '--filter', 'label=com.docker.compose.project=nap-handoff',
                   '--filter', 'label=com.docker.compose.service=api', '-q'], stdout=subprocess.PIPE).stdout.strip()
    if running:
        raise ValueError('Detener API antes de restaurar')
    if sql(container, "SELECT count(*) FROM pg_tables WHERE schemaname='public'", 'ps_user', 'ps_db') != '0':
        raise ValueError('La base destino debe estar vacía')
    verify(directory)
    with (directory / 'portal.dump').open('rb') as source:
        run(['docker', 'exec', '-i', container, 'pg_restore', '--exit-on-error', '--single-transaction',
             '--no-owner', '--no-privileges', '-U', 'ps_user', '-d', 'ps_db'], stdin=source, stdout=subprocess.PIPE)
    manifest = json.loads((directory / 'manifest.json').read_bytes())
    actual = inventory(container, 'ps_user', 'ps_db')
    if any(actual[key] != manifest[key] for key in actual):
        raise ValueError('Recuentos de destino no confirmados; no iniciar API')
    print('Base de traspaso restaurada; revisión y recuentos coinciden.')


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest='action', required=True)
    init = actions.add_parser('init');init.add_argument('--keyring', type=Path)
    create = actions.add_parser('export');create.add_argument('--directory', type=Path, required=True)
    create.add_argument('--db-container', default='ps_postgres');create.add_argument('--api-container', default='ps_backend')
    check = actions.add_parser('verify');check.add_argument('--directory', type=Path, required=True)
    load = actions.add_parser('restore');load.add_argument('--directory', type=Path, required=True)
    load.add_argument('--container', default='nap-handoff-db-1')
    args = parser.parse_args()
    try:
        if args.action == 'init':init_env(args.keyring)
        elif args.action == 'export':export(args.directory, args.db_container, args.api_container)
        elif args.action == 'verify':verify(args.directory)
        else:restore(args.directory, args.container)
        return 0
    except Exception as exc:
        print('No completado (' + type(exc).__name__ + '). Revisar archivos/permisos/Docker; no se imprimen secretos.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
