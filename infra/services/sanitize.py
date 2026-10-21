"""Saneamiento de una copia privada de rootfs, nunca de un sistema en marcha."""
import os
from pathlib import Path
import shutil


class ImageError(Exception):
    def __init__(self, message='La imagen no cumple las condiciones de construcción'):
        super().__init__(message)


MARKER = 'nap-image-builder/1\n'
CLEAR = ['root', 'home', 'tmp', 'var/tmp', 'run', 'var/log', 'var/lib/cloud',
    'var/cache/apt', 'var/lib/apt/lists',
    'var/lib/nap', 'etc/nap/postgresql', 'etc/nap/bookstack',
    'var/lib/postgresql/16', 'etc/postgresql/16', 'var/lib/mysql',
    'etc/ssl/private', 'etc/apt/auth.conf.d', 'etc/sudoers.d',
    'var/www/bookstack/public/uploads', 'var/www/bookstack/storage/uploads',
    'var/www/bookstack/storage/logs', 'var/www/bookstack/storage/framework/cache',
    'var/www/bookstack/storage/framework/sessions', 'var/www/bookstack/storage/framework/views',
    'var/www/bookstack/bootstrap/cache', 'var/www/bookstack/themes']
REMOVE = ['var/lib/systemd/random-seed', 'etc/mysql/debian.cnf', 'etc/apt/auth.conf',
    'etc/passwd-', 'etc/shadow-', 'etc/group-', 'etc/gshadow-', 'etc/security/opasswd',
    'etc/systemd/system/multi-user.target.wants/ssh.service',
    'etc/systemd/system/sockets.target.wants/ssh.socket']


def workspace_root(root):
    root = Path(root).absolute()
    if root.name != 'rootfs' or len(root.parts) < 4 or root.resolve() != root or not root.is_dir():
        raise ImageError('Se requiere una copia privada identificada como rootfs')
    marker = root / '.nap-build-workspace'
    if marker.is_symlink() or not marker.is_file() or marker.read_text() != MARKER:
        raise ImageError('Falta la marca del workspace de construcción')
    if root.stat().st_uid not in {0, os.geteuid()} or root.stat().st_mode & 0o022:
        raise ImageError('El workspace debe ser privado')
    return root


def confined(root, relative, *, regular=False):
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts:
        raise ImageError('Ruta fuera del rootfs')
    current = root
    for part in path.parts[:-1]:
        current /= part
        if current.is_symlink() or (current.exists() and not current.is_dir()):
            raise ImageError('Un directorio del rootfs no es seguro')
    target = root / path
    if regular and (target.is_symlink() or (target.exists() and not target.is_file())):
        raise ImageError('Se esperaba un archivo regular del rootfs')
    return target


def _remove(path):
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def _write(path, content, mode):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        path.unlink()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, mode)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, 'w', closefd=False) as output:
            output.write(content)
    finally:
        os.close(fd)


def sanitize_rootfs(root, product):
    if product not in {'linux', 'postgresql', 'bookstack'}:
        raise ImageError('Producto no permitido')
    root = workspace_root(root)
    # Comprobar todo antes de cambiar cuentas o eliminar datos. El workspace
    # privado no admite procesos invitados concurrentes ni puntos montados.
    for parent, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            path = Path(parent) / name
            if not path.is_symlink() and (path.is_mount() or (path.exists() and not (path.is_dir() or path.is_file()))):
                raise ImageError('El rootfs contiene un montaje o archivo especial')
    targets = [confined(root, path) for path in CLEAR + REMOVE]
    records = {name: confined(root, 'etc/' + name, regular=True) for name in ['passwd', 'shadow', 'group', 'gshadow', 'subuid', 'subgid']}
    for path in ['etc/machine-id', 'var/lib/dbus/machine-id', 'etc/sudoers', 'etc/systemd/system/ssh.service', 'etc/systemd/system/ssh.socket']:
        confined(root, path)
    ssh = confined(root, 'etc/ssh')
    web = confined(root, 'var/www/bookstack')
    if ssh.is_symlink() or web.is_symlink():
        raise ImageError('Directorio de preparación simbólico')
    extras = list(ssh.glob('ssh_host_*')) if ssh.exists() else []
    extras += list(web.glob('.env*')) if web.exists() else []
    kept = set()
    contents = {}
    try:
        for line in records['passwd'].read_text().splitlines():
            fields = line.split(':')
            if len(fields) != 7:
                raise ValueError()
            uid = int(fields[2])
            if (uid < 1000 or uid == 65534) and fields[0] != 'napadmin':
                kept.add(fields[0])
                contents.setdefault('passwd', []).append(line)
        if 'root' not in kept:
            raise ValueError()
        for name in ['shadow', 'group', 'gshadow', 'subuid', 'subgid']:
            if not records[name].exists():
                continue
            contents[name] = []
            for line in records[name].read_text().splitlines():
                fields = line.split(':')
                if name in {'shadow', 'subuid', 'subgid'}:
                    if fields[0] not in kept:
                        continue
                    if name == 'shadow':
                        if len(fields) != 9:
                            raise ValueError()
                        fields[1] = '!'
                elif name == 'group':
                    if len(fields) != 4:
                        raise ValueError()
                    gid = int(fields[2])
                    if gid >= 1000 and gid != 65534:
                        continue
                    fields[3] = ','.join(user for user in fields[3].split(',') if user in kept)
                else:
                    if len(fields) != 4:
                        raise ValueError()
                    fields[1] = '!'
                    fields[2] = ','.join(user for user in fields[2].split(',') if user in kept)
                    fields[3] = ','.join(user for user in fields[3].split(',') if user in kept)
                    if fields[0] not in {entry.split(':')[0] for entry in contents.get('group', [])}:
                        continue
                contents[name].append(':'.join(fields))
    except (ValueError, IndexError, OSError):
        raise ImageError('Inventario de cuentas inválido') from None
    for target in targets + extras:
        _remove(target)
    for name, lines in contents.items():
        _write(records[name], '\n'.join(lines) + '\n', 0o600 if name in {'shadow', 'gshadow'} else 0o644)
    for relative in ['etc/machine-id', 'var/lib/dbus/machine-id']:
        _write(confined(root, relative), '', 0o644)
    _write(confined(root, 'etc/sudoers'), 'Defaults env_reset\nroot ALL=(ALL:ALL) ALL\n%sudo ALL=(ALL:ALL) ALL\n@includedir /etc/sudoers.d\n', 0o440)
    for relative, mode in [('root', 0o700), ('home', 0o755), ('tmp', 0o1777), ('var/tmp', 0o1777), ('run', 0o755), ('var/log', 0o755), ('etc/sudoers.d', 0o750)]:
        path = confined(root, relative)
        path.mkdir(parents=True, exist_ok=True)
        path.chmod(mode)
    for unit in ['ssh.service', 'ssh.socket']:
        path = confined(root, 'etc/systemd/system/' + unit)
        _remove(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to('/dev/null')
