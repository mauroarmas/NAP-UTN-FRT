"""Copiar seis artefactos revisados sin sobrescribir ni habilitar recetas.

Sin --apply sólo inspecciona. No ejecuta comandos PVE ni cambia registro,
cuentas, ACL, red o invitados. La CLI aplicada requiere consola/root en PVE.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile

PRODUCTS = ('linux', 'postgresql', 'bookstack')
TARGETS = {'image': Path('/var/lib/vz/template/cache'), 'bundle': Path('/opt/nap/recipes')}
MAX_SIZE = {'image': 512 * 1024**2, 'bundle': 2 * 1024**2}


def digest(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as source:
        info = os.fstat(source.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid not in {0, os.geteuid()}
                or info.st_mode & 0o022 or info.st_nlink != 1 or info.st_size > MAX_SIZE['image']):
            raise ValueError('Artefacto no regular, enlazado, modificable o demasiado grande')
        value = hashlib.file_digest(source, 'sha256').hexdigest()
        return value, info.st_size


def secure_path(path):
    path = Path(path).absolute()
    for part in [*reversed(path.parents), path]:
        if part.is_symlink(): raise ValueError('No se admiten enlaces en las rutas')
        if part.exists():
            info = part.stat()
            sticky_ancestor = part != path and info.st_uid == 0 and info.st_mode & stat.S_ISVTX
            if info.st_uid not in {0, os.geteuid()} or info.st_mode & 0o022 and not sticky_ancestor:
                raise ValueError('Directorio de artefactos no controlado por el operador')
    return path


def index_from(source, expected):
    source = secure_path(source)
    path = source / 'artifact-index.json'
    checksum, size = digest(path)
    if checksum != expected or size > 65536: raise ValueError('Índice diferente al revisado o demasiado grande')
    def unique(items):
        result = {}
        for key, value in items:
            if key in result: raise ValueError('Clave repetida')
            result[key] = value
        return result
    data = json.loads(path.read_text(), object_pairs_hook=unique)
    if not isinstance(data, dict) or set(data) != {'schema_version', 'artifacts'} or type(data['schema_version']) is not int or data['schema_version'] != 1:
        raise ValueError('Índice desconocido')
    if not isinstance(data['artifacts'], list) or len(data['artifacts']) != 6: raise ValueError('Se esperan tres imágenes y tres bundles')
    found = set()
    for item in data['artifacts']:
        if not isinstance(item, dict) or set(item) != {'product', 'kind', 'sha256', 'size'}: raise ValueError('Entrada desconocida')
        product, kind = item['product'], item['kind']
        if product not in PRODUCTS or kind not in TARGETS or (product, kind) in found: raise ValueError('Producto/tipo repetido o desconocido')
        found.add((product, kind))
        if not isinstance(item['sha256'], str) or not re.fullmatch('[a-f0-9]{64}', item['sha256']): raise ValueError('SHA inválido')
        if type(item['size']) is not int or not 0 < item['size'] <= MAX_SIZE[kind]: raise ValueError('Tamaño inválido')
    return data['artifacts']


def filename(item):
    return (f"nap009-{item['product']}-1.0.0.tar.gz" if item['kind'] == 'image'
            else f"nap009-{item['product']}-1.0.0-{item['sha256']}.tar.gz")


def inspect_plan(source, expected, *, targets=None):
    targets = targets or TARGETS
    result = []
    for item in index_from(source, expected):
        entry = Path(source) / f"{item['product']}-{item['kind']}.tar.gz"
        if digest(entry) != (item['sha256'], item['size']): raise ValueError('Hash o tamaño de origen incorrecto')
        parent = secure_path(targets[item['kind']])
        target = parent / filename(item)
        existing = target.exists() or target.is_symlink()
        if existing and digest(target) != (item['sha256'], item['size']): raise ValueError('El destino existe con otro contenido; no se reemplaza')
        result.append({**item, 'source': entry, 'target': target, 'existing': existing})
    return result


def copy_exclusive(item):
    """Verificar los mismos bytes que se copian; publicación exclusiva sin replace."""
    parent, target = item['target'].parent, item['target']
    fd, temporary = tempfile.mkstemp(prefix='.nap009-', dir=parent)
    try:
        with os.fdopen(fd, 'wb') as output:
            fd_source = os.open(item['source'], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd_source, 'rb') as source:
                info = os.fstat(source.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1: raise ValueError('Origen cambió')
                checksum, size = hashlib.sha256(), 0
                while chunk := source.read(1024**2):
                    size += len(chunk)
                    if size > item['size']: raise ValueError('Origen cambió de tamaño')
                    checksum.update(chunk); output.write(chunk)
            if (checksum.hexdigest(), size) != (item['sha256'], item['size']): raise ValueError('Origen cambió de contenido')
            output.flush(); os.fsync(output.fileno()); os.fchmod(output.fileno(), 0o444)
        os.link(temporary, target, follow_symlinks=False)  # Nunca sustituir otro archivo.
        return target.stat().st_ino
    finally:
        Path(temporary).unlink(missing_ok=True)


def install(source, expected, *, apply=False, targets=None):
    plan = inspect_plan(source, expected, targets=targets)
    created = []
    try:
        if apply:
            for item in plan:
                if item['existing']: continue
                item['target'].parent.mkdir(parents=True, exist_ok=True, mode=0o755)
                secure_path(item['target'].parent)
                inode = copy_exclusive(item)
                created.append((item['target'], inode))
            for directory in {item['target'].parent for item in plan}:
                fd = os.open(directory, os.O_DIRECTORY)
                try: os.fsync(fd)
                finally: os.close(fd)
    except BaseException:
        # Sólo archivos creados por esta ejecución y que conservan su inode.
        for path, inode in reversed(created):
            if not path.is_symlink() and path.exists() and path.stat().st_ino == inode: path.unlink()
        raise
    return {'estado': 'artefactos_copiados' if apply else 'plan_sin_cambios', 'archivos': [
        {'producto': item['product'], 'tipo': item['kind'], 'destino': str(item['target']),
         'sha256':item['sha256'], 'bytes':item['size'], 'ya_existia':item['existing']} for item in plan],
        'pendiente': 'Registro/perfiles/red/TLS/permisos/ensayos; no se habilitó ninguna receta ni invitado'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--index-sha256', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if args.apply and (os.geteuid() != 0 or not Path('/etc/pve').is_dir()):
        parser.error('--apply requiere root en el nodo PVE, no en la PC de desarrollo')
    try:
        if args.apply:
            fd = os.open('/run/lock/nap009-artifacts.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'w') as lock:
                info = os.fstat(lock.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_nlink != 1 or info.st_mode & 0o077:
                    raise ValueError('Lock de instalación no privado/root')
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                result = install(args.source, args.index_sha256, apply=True)
        else: result = install(args.source, args.index_sha256)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as exc:
        print(json.dumps({'estado':'no_instalado', 'tipo':type(exc).__name__,
                          'mensaje':'Revisar hashes, permisos y destinos existentes; no se reemplazan archivos'}))
        return 1
    return 0


if __name__ == '__main__': raise SystemExit(main())
