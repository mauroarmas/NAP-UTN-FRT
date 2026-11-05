"""Preparación inicial, explícita y sin contraseñas, de la cuenta SSH del nodo.

Por defecto muestra el plan. --apply solo se ejecuta como root en PVE desde una
copia root del paquete. No publica definiciones ni configura red/ACL de docentes.
"""
import argparse
import base64
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import pwd
import stat
import subprocess
import tempfile


COMMAND = '/usr/bin/sudo -n /usr/local/sbin/nap-guest-runner'
EXPECTED = {
    'forcecommand': COMMAND,
    'authenticationmethods': 'publickey',
    'pubkeyauthentication': 'yes',
    'passwordauthentication': 'no',
    'kbdinteractiveauthentication': 'no',
    'disableforwarding': 'yes',
    'permittty': 'no',
    'permituserrc': 'no',
    'authorizedkeysfile': '/etc/nap/runner/authorized_keys',
    'authorizedkeyscommand': 'none',
    'trustedusercakeys': 'none',
}


def access_files(worker_ip, public_key):
    address = ipaddress.ip_address(worker_ip)
    if address.is_unspecified or address.is_multicast or address.is_loopback:
        raise ValueError('Usar una dirección de origen unicast concreta del worker')
    lines = public_key.strip().splitlines()
    fields = lines[0].split() if len(lines) == 1 else []
    if len(fields) < 2 or fields[0] != 'ssh-ed25519':
        raise ValueError('Se requiere una sola clave pública Ed25519 sin opciones')
    try:
        blob = base64.b64decode(fields[1], validate=True)
    except ValueError:
        raise ValueError('Clave pública inválida') from None
    if len(blob) != 51 or not blob.startswith(b'\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20'):
        raise ValueError('Clave pública inválida')
    cidr = str(address) + ('/32' if address.version == 4 else '/128')
    key = f'restrict,from="{cidr}",command="{COMMAND}" ssh-ed25519 {fields[1]} nap-worker\n'
    ssh = '# Gestionado por NAP; cuenta dedicada, sin shell libre.\nMatch User naprunner\n'
    ssh += ''.join('    ' + name + ' ' + value + '\n' for name, value in {
        'ForceCommand': COMMAND, 'AuthenticationMethods': 'publickey',
        'PubkeyAuthentication': 'yes', 'PasswordAuthentication': 'no',
        'KbdInteractiveAuthentication': 'no', 'DisableForwarding': 'yes',
        'PermitTTY': 'no', 'PermitUserRC': 'no',
        'AuthorizedKeysFile': '/etc/nap/runner/authorized_keys',
        'AuthorizedKeysCommand': 'none', 'TrustedUserCAKeys': 'none',
    }.items())
    ssh += 'Match all\n'
    sudo = ('Defaults:naprunner env_reset, !setenv, !log_input, !log_output\n'
        'naprunner ALL=(root) NOPASSWD: /usr/local/sbin/nap-guest-runner ""\n')
    return {
        '/etc/nap/runner/authorized_keys': (key, 0o644),
        '/etc/sudoers.d/naprunner': (sudo, 0o440),
        '/etc/ssh/sshd_config.d/00-naprunner.conf': (ssh, 0o644),
    }


def ensure_new_paths(paths):
    for name in paths:
        path = Path(name)
        if not path.is_absolute() or path.exists() or path.is_symlink():
            raise ValueError(f'Destino existente o inválido; no se reemplaza: {path}')
        for parent in path.parents:
            if parent.is_symlink() or (parent.exists() and (
                not parent.is_dir() or parent.stat().st_mode & 0o022)):
                raise ValueError(f'Directorio inseguro: {parent}')


def validate_effective(value):
    settings = dict(line.split(' ', 1) for line in value.splitlines() if ' ' in line)
    if any(settings.get(name) != expected for name, expected in EXPECTED.items()):
        raise ValueError('sshd no aplica todas las restricciones esperadas; no se activa')


def commit_files(files, check, activate):
    """No sobrescribir; si falla comprobación/recarga retirar solo archivos nuevos."""
    written, activating = [], False
    try:
        for name, (content, mode) in files.items():
            path = Path(name)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
            written.append(path)
            with os.fdopen(fd, 'wb') as output:
                os.fchmod(output.fileno(), mode)
                output.write(content.encode() if isinstance(content, str) else content)
                output.flush()
                os.fsync(output.fileno())
        check()
        activating = True
        activate()
    except BaseException:
        for path in reversed(written):
            path.unlink(missing_ok=True)
        if activating:
            activate()
        raise


def command(argv, *, input=None):
    result = subprocess.run(argv, input=input, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, timeout=30, check=True,
        env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C.UTF-8'})
    return result.stdout.decode()


def apply(source_root, files, worker_ip, node_ip):
    if os.geteuid() != 0 or not Path('/etc/pve').is_dir():
        raise ValueError('--apply requiere root en el nodo Proxmox')
    required = ['/usr/sbin/sshd', '/usr/sbin/visudo', '/usr/bin/sudo', '/usr/sbin/pct',
        '/usr/bin/pvesh', '/usr/sbin/useradd', '/usr/sbin/runuser', '/usr/bin/systemctl']
    missing = [name for name in required if not os.access(name, os.X_OK)]
    if missing:
        raise ValueError('Faltan prerrequisitos: ' + ', '.join(missing)
            + '. Si falta sudo: apt-get update && apt-get install --no-install-recommends sudo')
    try:
        pwd.getpwnam('naprunner')
    except KeyError:
        pass
    else:
        raise ValueError('naprunner ya existe; revisar su origen, no se reutiliza automáticamente')
    # useradd -U también rechaza un grupo existente; comprobarlo antes de escribir.
    import grp
    try:
        grp.getgrnam('naprunner')
    except KeyError:
        pass
    else:
        raise ValueError('El grupo naprunner ya existe; revisar antes de continuar')
    runtime = {
        '/opt/nap/runner/nap_guest_runner.py': 'infra/runner/nap_guest_runner.py',
        '/opt/nap/runner/node_executor.py': 'infra/runner/node_executor.py',
        '/opt/nap/runner/protocol.py': 'backend/app/schemas/guest_runner.py',
        '/opt/nap/runner/registry_entries.py': 'backend/app/utils/artifact_registry.py',
        '/usr/local/sbin/nap-guest-runner': 'infra/runner/nap-guest-runner',
    }
    for parent in (source_root, *source_root.parents):
        if parent.stat().st_uid != 0 or parent.stat().st_mode & 0o022:
            raise ValueError('La copia del paquete debe estar en un directorio root seguro')
    for target, relative in runtime.items():
        source = source_root / relative
        if source.is_symlink() or source.resolve() != source or not source.is_file():
            raise ValueError('Fuente ausente o enlazada: ' + relative)
        info = source.stat()
        if info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError('La copia revisada debe pertenecer a root: ' + relative)
        files[target] = (source.read_bytes(), 0o755 if target.endswith('/nap-guest-runner') else 0o444)
    files['/etc/nap/runner/registry.json'] = ('{}\n', 0o600)
    # No adoptar estado, home ni registro de otra instalación.
    ensure_new_paths([*files, '/var/lib/nap-runner', '/var/lib/nap-runner-login'])
    # No ampliar permisos de un directorio privado preexistente. Los nuevos
    # reciben el modo explícito más abajo, independientemente de la umask.
    for name in ('/etc/nap', '/etc/nap/runner'):
        path = Path(name)
        if path.exists() and not path.stat().st_mode & 0o001:
            raise ValueError('El directorio preexistente no permite recorrer authorized_keys: ' + name)
    connection = 'host=worker,user=naprunner,addr=' + str(ipaddress.ip_address(worker_ip))
    connection += ',laddr=' + str(ipaddress.ip_address(node_ip)) + ',lport=22'
    root_connection = connection.replace('user=naprunner', 'user=root')
    command(['/usr/sbin/sshd', '-t'])
    baseline = command(['/usr/sbin/sshd', '-T', '-C', root_connection])
    # Validar sudo antes de escribir en /etc. El directorio temporal es privado.
    with tempfile.TemporaryDirectory(prefix='nap-access-') as temporary:
        candidate = Path(temporary) / 'sudoers'
        candidate.write_text(files['/etc/sudoers.d/naprunner'][0])
        candidate.chmod(0o440)
        command(['/usr/sbin/visudo', '-cf', str(candidate)])
    for directory, mode in {
        '/opt/nap': 0o755, '/opt/nap/runner': 0o755, '/etc/nap': 0o755,
        '/etc/nap/runner': 0o755, '/var/lib/nap-runner': 0o700,
        '/var/lib/nap-runner-login': 0o755, '/etc/ssh/sshd_config.d': 0o755,
    }.items():
        path = Path(directory)
        if path.exists():
            if path.stat().st_uid != 0:
                raise ValueError('Directorio no root: ' + directory)
        else:
            path.mkdir(mode=mode)
            # mkdir aplica la umask del operador. El paquete remoto usa 077:
            # los directorios de authorized_keys/home deben seguir siendo
            # recorribles por sshd al verificar la clave como naprunner.
            path.chmod(mode)

    def check():
        command(['/usr/sbin/visudo', '-cf', '/etc/sudoers.d/naprunner'])
        command(['/usr/sbin/sshd', '-t'])
        validate_effective(command(['/usr/sbin/sshd', '-T', '-C', connection]))
        if command(['/usr/sbin/sshd', '-T', '-C', root_connection]) != baseline:
            raise ValueError('La configuración efectiva de root cambió; se retira el fragmento')
        command(['/usr/sbin/useradd', '--system', '--user-group', '--no-create-home',
            '--home-dir', '/var/lib/nap-runner-login', '--shell', '/bin/sh', 'naprunner'])
        result = json.loads(command(['/usr/sbin/runuser', '-u', 'naprunner', '--',
            '/usr/bin/sudo', '-n', '/usr/local/sbin/nap-guest-runner'], input=b'{}'))
        if result.get('error', {}).get('code') != 'INVALID_REQUEST' or result.get('identity_verified') is not False:
            raise ValueError('No se verificó el wrapper como naprunner')

    commit_files(files, check, lambda: command(['/usr/bin/systemctl', 'reload', 'ssh']))
    return {name: hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()
        for name, (value, _) in files.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker-ip', required=True)
    parser.add_argument('--node-ip', required=True)
    parser.add_argument('--public-key', required=True, type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    try:
        ipaddress.ip_address(args.node_ip)
        files = access_files(args.worker_ip, args.public_key.read_text())
        if not args.apply:
            for name, (value, mode) in files.items():
                print(f'{name} ({mode:04o})\n{value}')
            print('Plan solamente. --apply requiere root en PVE; no se modificó el equipo.')
            return
        lock = os.open('/run/lock/nap-runner-setup.lock',
            os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(lock)
            if info.st_uid != 0 or not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
                raise ValueError('Lock de instalación inseguro')
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            receipt = apply(Path(__file__).resolve().parents[2], files, args.worker_ip, args.node_ip)
        finally:
            os.close(lock)
        print(json.dumps({'estado': 'acceso_instalado', 'archivos_sha256': receipt}, indent=2))
        print('Faltan prueba SSH, registro de recetas/red y aceptación T101/T102.')
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print('Preparación no completada: ' + str(exc), file=__import__('sys').stderr)
        print('Conservar consola root. Si se creó naprunner antes del fallo, su revisión es manual.',
            file=__import__('sys').stderr)
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
