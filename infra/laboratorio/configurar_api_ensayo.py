"""Acceso temporal de staging. Plan por defecto; nunca modifica invitados.

Solo biblioteca estándar para el nodo. El secreto se conserva en un archivo
root nuevo antes de habilitar la cuenta; stdout ordinario no contiene el token.
"""
import argparse
import json
import os
from pathlib import Path
import socket
import ssl
import stat
import subprocess
import sys
import tempfile
import time
import hashlib
import fcntl

HOST = '172.16.36.100'
USER = 'nap009lab@pve'
TOKEN_NAME = 'ensayos'
TOKEN = USER + '!' + TOKEN_NAME
POOL = 'nap009-staging'
COMMENT = 'Spec009: staging temporal; sin invitados preexistentes'
SECRET_PATH = Path('/root/nap009-api-ensayos.json')
ROLES = {
    'NAP009LabAudit': ['VM.Audit', 'Sys.Audit', 'Datastore.Audit'],
    'NAP009LabGuest': ['Pool.Audit', 'VM.Audit', 'VM.Allocate', 'VM.PowerMgmt',
        'VM.Config.CPU', 'VM.Config.Memory', 'VM.Config.Disk',
        'VM.Config.Network', 'VM.Config.Options'],
    'NAP009LabDisk': ['Datastore.AllocateSpace'],
    'NAP009LabBridge': ['SDN.Use'],
}
GRANTS = {'/': 'NAP009LabAudit', '/pool/'+POOL: 'NAP009LabGuest',
    '/storage/local-lvm': 'NAP009LabDisk',
    '/sdn/zones/localnetwork/vmbr0': 'NAP009LabBridge'}


class PreparationError(ValueError):
    """Código cerrado que puede mostrarse sin revelar respuestas o secretos."""


class PVECommandError(RuntimeError):
    def __init__(self, method, route, returncode):
        self.operation = {'metodo': method, 'ruta': route, 'salida': returncode}
        super().__init__('PVE_NO_CONFIRMADO')


def integer(value):
    # El JSON de pvesh puede conservar escalares numéricos como strings.
    if type(value) is int:
        return value
    if type(value) is str and value.isascii() and value.isdigit() and str(int(value)) == value:
        return int(value)
    raise PreparationError('NUMERO_PVE_INVALIDO')


def token_private(token, *, ca, expire, handle):
    # Conservar ANTES de validar: PVE sólo devuelve el secreto al crearlo.
    _save(handle, {'estado': 'respuesta_token_pendiente_revision', 'usuario': USER,
        'token_response': token})
    if not isinstance(token, dict) or token.get('full-tokenid') != TOKEN:
        raise PreparationError('IDENTIDAD_TOKEN_NO_CONFIRMADA')
    if not isinstance(token.get('value'), str) or not token['value']:
        raise PreparationError('SECRETO_TOKEN_NO_CONFIRMADO')
    info = token.get('info', {})
    if (1 if info.get('privsep') is True else integer(info.get('privsep'))) != 1:
        raise PreparationError('PRIVSEP_TOKEN_NO_CONFIRMADO')
    if integer(info.get('expire')) != expire:
        raise PreparationError('VENCIMIENTO_TOKEN_NO_CONFIRMADO')
    private = {'estado': 'token_guardado_cuenta_pendiente', 'proxmox_host': HOST,
        'proxmox_port': 8006, 'proxmox_user': USER,
        'proxmox_token_name': TOKEN_NAME, 'proxmox_token_value': token['value'],
        'proxmox_verify_ssl': True, 'ca_pem': ca, 'expire': expire, 'pool': POOL}
    _save(handle, private)
    return private


def verify_tls(ca):
    context = ssl.create_default_context(cadata=ca)
    with socket.create_connection((HOST, 8006), timeout=10) as connection:
        with context.wrap_socket(connection, server_hostname=HOST):
            pass


def local_command(argv):
    result = subprocess.run(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        timeout=95, env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C.UTF-8'})
    if result.returncode:
        raise RuntimeError('Comando de certificado no confirmado; conservar respaldo y revisar')


def repair_default_tls(ca, *, root=Path('/'), probe=verify_tls, run=local_command):
    """Sólo error de IP, nodo standalone conocido y certificado PVE predeterminado.

    No cambia red, hosts, CA ni claves SSH. Pvecm actualiza sus metadatos locales.
    El respaldo contiene una clave privada y permanece exclusivamente en root.
    """
    try:
        probe(ca)
        return {'renovado': False}
    except ssl.SSLCertVerificationError as error:
        if error.verify_code != 64:
            raise PreparationError('TLS_NO_ES_ERROR_DE_IP') from None
    node = root/'etc/pve/nodes/proxmox'
    if ((root/'etc/pve/corosync.conf').exists()
        or (node/'pveproxy-ssl.pem').exists() or (node/'pveproxy-ssl.pem').is_symlink()
        or (node/'pveproxy-ssl.key').exists() or (node/'pveproxy-ssl.key').is_symlink()
        or socket.gethostname().split('.')[0] != 'proxmox'):
        raise PreparationError('NODO_CLUSTER_O_CERTIFICADO_PERSONALIZADO')
    addresses = {row[4][0] for row in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)}
    if addresses != {HOST}:
        raise PreparationError('RESOLUCION_LOCAL_NO_COINCIDE_CON_IP_ACTUAL')
    paths = {'pve-ssl.pem': node/'pve-ssl.pem', 'pve-ssl.key': node/'pve-ssl.key',
        'ca.pem': root/'etc/pve/pve-root-ca.pem',
        'ssh_host_ed25519_key.pub': root/'etc/ssh/ssh_host_ed25519_key.pub'}
    originals = {}
    for name, path in paths.items():
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_size > 65536:
                raise PreparationError('ARCHIVO_DE_IDENTIDAD_NO_CONFIABLE')
            originals[name] = handle.read(65537)
    if originals['ca.pem'].decode() != ca:
        raise PreparationError('CA_CAMBIO_DURANTE_INSPECCION')
    backup = Path(tempfile.mkdtemp(prefix='nap009-tls-respaldo-', dir=root/'root'))
    backup.chmod(0o700)
    for name, data in originals.items():
        fd = os.open(backup/name, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data); handle.flush(); os.fsync(handle.fileno())
    # Herramienta oficial: no sustituir CA ni firmar certificados manualmente.
    run(['/usr/bin/pvecm', 'updatecerts', '--force'])
    run(['/usr/bin/systemctl', 'reload', 'pveproxy'])
    for name in ('ca.pem', 'ssh_host_ed25519_key.pub'):
        if paths[name].read_bytes() != originals[name]:
            raise PreparationError('IDENTIDAD_CAMBIO_REVISAR_RESPALDO_ROOT')
    last_error = None
    for attempt in range(8):
        try:
            probe(ca)
            return {'renovado': True, 'respaldo_root': str(backup),
                'ca_sha256': hashlib.sha256(originals['ca.pem']).hexdigest(),
                'ca_y_hostkey_ssh_conservadas': True}
        except (ssl.SSLError, OSError) as error:
            last_error = error
            if attempt < 7: time.sleep(0.5)
    raise last_error


def pvesh(method, route, **params):
    argv = ['/usr/bin/pvesh', method, route, '--output-format', 'json']
    for key, value in params.items():
        argv.extend(['--'+key, str(value)])
    result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        timeout=30, check=False, env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C.UTF-8'})
    if result.returncode or len(result.stdout) > 2*1024*1024:
        raise PVECommandError(method, route, result.returncode)
    return json.loads(result.stdout) if result.stdout.strip() else None


def _save(handle, value):
    handle.seek(0)
    handle.truncate()
    json.dump(value, handle, ensure_ascii=False)
    handle.write('\n')
    handle.flush()
    os.fsync(handle.fileno())


def configure(call, *, ca, apply=False, secret_path=SECRET_PATH, now=None):
    # Colisiones bloquean TODO antes de la primera mutación. No adoptar cuentas,
    # pools o roles existentes, aunque parezcan compatibles.
    users = call('get', '/access/users')
    roles = call('get', '/access/roles')
    pools = call('get', '/pools')
    if (any(row['userid'] == USER for row in users)
        or any(row['roleid'] in ROLES for row in roles)
        or any(row['poolid'] == POOL for row in pools)):
        raise ValueError('Namespace existente: revisar antes de reintentar; no se adoptó ni reemplazó')
    resources = call('get', '/cluster/resources', type='vm')
    report = {'estado': 'plan_sin_cambios', 'usuario': USER, 'token_id': TOKEN,
        'pool': POOL, 'roles': ROLES, 'grants': GRANTS, 'privsep': 1,
        'vigencia_dias': 30, 'inventario_solo_lectura': [
            {k: row.get(k) for k in ('vmid', 'type', 'status')} for row in resources],
        'consolas_y_ensayos_no_acreditados': True}
    if not apply:
        return report
    expire = int(now if now is not None else time.time()) + 30*86400
    fd = os.open(secret_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    created_user = False
    with os.fdopen(fd, 'w', encoding='utf-8') as handle:
        os.fchmod(handle.fileno(), 0o600)
        _save(handle, {'estado': 'incompleto_revisar', 'usuario': USER})
        try:
            # Crear deshabilitada: un timeout inicial conserva ese estado seguro.
            call('create', '/access/users', userid=USER, enable=0, expire=expire, comment=COMMENT)
            created_user = True
            call('create', '/pools', poolid=POOL, comment=COMMENT)
            for name, privileges in ROLES.items():
                call('create', '/access/roles', roleid=name, privs=','.join(privileges))
            token = call('create', '/access/users/'+USER+'/token/'+TOKEN_NAME,
                privsep=1, expire=expire, comment=COMMENT)
            private = token_private(token, ca=ca, expire=expire, handle=handle)
            for path, role in GRANTS.items():
                for subject, identity in [('users', USER), ('tokens', TOKEN)]:
                    call('set', '/access/acl', path=path, roles=role, propagate=1, **{subject: identity})
            call('set', '/access/users/'+USER, enable=1)
            private['estado'] = 'configurado_pendiente_verificacion_api'
            _save(handle, private)
        except Exception:
            if created_user:
                # No borrar roles/pool: pueden haber quedado operaciones inciertas.
                try: call('set', '/access/users/'+USER, enable=0)
                except Exception: pass
            raise
    report['estado'] = 'configurado_pendiente_verificacion_api'
    report['expire'] = expire
    return report


def recovery_snapshot(call):
    users = [row for row in call('get', '/access/users') if row.get('userid') == USER]
    if len(users) != 1:
        raise PreparationError('USUARIO_RECUPERACION_NO_UNICO')
    user = users[0]
    groups = user.get('groups') or []
    if isinstance(groups, str): groups = groups.split(',')
    account = {'userid': USER, 'enable': integer(user.get('enable')),
        'expire': integer(user.get('expire')), 'comment': user.get('comment'), 'groups': sorted(groups)}
    roles = {row['roleid']: sorted(row['privs'].replace(' ', ',').split(','))
        for row in call('get', '/access/roles') if row.get('roleid', '').startswith('NAP009Lab')}
    pool = call('get', '/pools/'+POOL)
    tokens = [{'tokenid': row['tokenid'], 'privsep': integer(row['privsep']),
        'expire': integer(row['expire']), 'comment': row.get('comment')}
        for row in call('get', '/access/users/'+USER+'/token')]
    acl = [row for row in call('get', '/access/acl') if row.get('ugid') in {USER, TOKEN}]
    return {'usuario': account, 'roles': roles, 'pool': {'comment': pool.get('comment'),
        'members': pool.get('members', [])}, 'tokens': sorted(tokens, key=lambda r: r['tokenid']),
        'acl': sorted(acl, key=lambda r: json.dumps(r, sort_keys=True))}


def snapshot_sha(snapshot):
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def resume_reviewed(call, *, ca, expected_sha, secret_path=SECRET_PATH, now=None):
    """Recuperar sólo el intento propio, deshabilitado, vacío y sin ACL revisado.

    Una diferencia pública o privada detiene antes de toda mutación. No adopta
    configuraciones parecidas ni reinicia una recuperación parcial a ciegas.
    """
    fd = os.open(secret_path, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'r+', encoding='utf-8') as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        info = os.fstat(handle.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
            or info.st_mode & 0o077 or info.st_nlink != 1 or info.st_size > 65536):
            raise PreparationError('ESTADO_PRIVADO_NO_CONFIABLE')
        original = handle.read(65537)
        private = json.loads(original)
        snapshot = recovery_snapshot(call)
        if snapshot_sha(snapshot) != expected_sha:
            raise PreparationError('ESTADO_CAMBIO_DESDE_REVISION')
        account = snapshot['usuario']; expire = account['expire']
        current = int(now if now is not None else time.time())
        if (account['enable'] != 0 or account['groups'] or account['comment'] != COMMENT
            or not current < expire <= current + 31*86400
            or snapshot['roles'] != {name: sorted(privs) for name, privs in ROLES.items()}
            or snapshot['pool'] != {'comment': COMMENT, 'members': []} or snapshot['acl']
            or snapshot['tokens'] != [{'tokenid': TOKEN_NAME, 'privsep': 1, 'expire': expire, 'comment': COMMENT}]):
            raise PreparationError('ESTADO_NO_ES_EL_INTENTO_INCOMPLETO_REVISADO')
        orphan = private == {'estado': 'incompleto_revisar', 'usuario': USER}
        if not orphan:
            expected = {'estado': 'token_guardado_cuenta_pendiente', 'proxmox_host': HOST,
                'proxmox_port': 8006, 'proxmox_user': USER, 'proxmox_token_name': TOKEN_NAME,
                'proxmox_verify_ssl': True, 'ca_pem': ca, 'expire': expire, 'pool': POOL}
            if ({k: value for k, value in private.items() if k != 'proxmox_token_value'} != expected
                or not isinstance(private.get('proxmox_token_value'), str) or not private['proxmox_token_value']):
                raise PreparationError('MARCADOR_PRIVADO_NO_ES_DEL_INTENTO_REVISADO')
        backup = Path(tempfile.mkdtemp(prefix='nap009-api-respaldo-', dir=secret_path.parent))
        backup.chmod(0o700)
        backup_fd = os.open(backup/'estado.json', os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(backup_fd, 'w') as saved:
            saved.write(original); saved.flush(); os.fsync(saved.fileno())
        try:
            if orphan:
                _save(handle, {'estado': 'recuperacion_token_orfano_pendiente',
                    'usuario': USER, 'snapshot_sha256': expected_sha})
                route = '/access/users/'+USER+'/token/'+TOKEN_NAME
                call('delete', route)
                token = call('create', route, privsep=1, expire=expire, comment=COMMENT)
                private = token_private(token, ca=ca, expire=expire, handle=handle)
            for path, role in GRANTS.items():
                for subject, identity in [('users', USER), ('tokens', TOKEN)]:
                    call('set', '/access/acl', path=path, roles=role, propagate=1, **{subject: identity})
            call('set', '/access/users/'+USER, enable=1)
            private['estado'] = 'configurado_pendiente_verificacion_api'
            _save(handle, private)
        except Exception:
            try: call('set', '/access/users/'+USER, enable=0)
            except Exception: pass
            raise
    return {'estado': 'configurado_pendiente_verificacion_api', 'usuario': USER,
        'token_id': TOKEN, 'pool': POOL, 'expire': expire,
        'recuperacion_snapshot_sha256': expected_sha, 'token_orfano_reemitido': orphan,
        'respaldo_root': str(backup), 'consolas_y_ensayos_no_acreditados': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--resume-reviewed', metavar='SHA256', help='Recuperar sólo estado incompleto contrastado con snapshot revisado')
    parser.add_argument('--repair-default-tls', action='store_true', help='Renovar certificado PVE sólo ante IP antigua, con respaldo root')
    parser.add_argument('--export-private', action='store_true', help='Solo lanzador: stdout capturado en archivo privado')
    args = parser.parse_args()
    if os.geteuid() != 0 or not Path('/etc/pve').is_dir():
        parser.error('Ejecutar exclusivamente como root en el nodo PVE')
    if args.export_private and (not args.apply or sys.stdout.isatty()):
        parser.error('La exportación requiere aplicación y stdout privado, no una terminal')
    if args.repair_default_tls and not args.apply:
        parser.error('La renovación requiere --apply explícito')
    if args.resume_reviewed and (not args.apply or args.repair_default_tls
        or len(args.resume_reviewed) != 64 or any(c not in '0123456789abcdef' for c in args.resume_reviewed)):
        parser.error('La recuperación exige --apply, SHA revisado y no admite renovación TLS')
    stage = 'leer_ca'
    try:
        ca = Path('/etc/pve/pve-root-ca.pem').read_text()
        stage = 'verificar_tls'
        tls = repair_default_tls(ca) if args.repair_default_tls else (verify_tls(ca) or {'renovado': False})
        stage = 'preparar_api'
        report = (resume_reviewed(pvesh, ca=ca, expected_sha=args.resume_reviewed)
            if args.resume_reviewed else configure(pvesh, ca=ca, apply=args.apply))
        report['tls'] = tls
        if args.export_private:
            json.dump({'report': report, 'private': json.loads(SECRET_PATH.read_text())}, sys.stdout)
        else:
            print(json.dumps(report, ensure_ascii=False, indent=2))
    except Exception as error:
        # Nunca volcar stdout de pvesh, objetos de token ni errores con secretos.
        detail = {'etapa': stage, 'tipo': type(error).__name__}
        if isinstance(error, PreparationError):
            detail['codigo'] = str(error)
        if isinstance(error, PVECommandError):
            detail['operacion'] = error.operation
        if isinstance(error, ssl.SSLCertVerificationError):
            detail['tls_codigo'] = error.verify_code
            detail['tls_mensaje'] = error.verify_message
        print('Preparación no confirmada: '+json.dumps(detail, ensure_ascii=False)+'. Conservar respaldos root y revisar; no repetir sin diagnóstico.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
