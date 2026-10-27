"""Registrar únicamente Linux de staging sobre el registro vacío revisado.

No publica definiciones, crea invitados ni modifica cuentas, red o TLS.
Sólo biblioteca estándar: se ejecuta como root en PVE desde copia con SHA fijado.
"""
import argparse
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from uuid import UUID

KEY = 'linux-lab-009:1.0.0'
FIELDS = {'schema_version', 'previous_sha256', 'definition_sha256', 'cluster_uuid', 'bundle_sha256', 'image_sha256'}


def secure_parent(path):
    for directory in [*reversed(path.parent.parents), path.parent]:
        info = directory.lstat()
        sticky = info.st_uid == 0 and info.st_mode & stat.S_ISVTX
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid not in {0, os.geteuid()}
            or info.st_mode & 0o022 and not sticky):
            raise ValueError('Directorio no confiable')


def checked(path, *, limit, private=False, content=False):
    secure_parent(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as source:
        info = os.fstat(source.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
            or info.st_nlink != 1 or info.st_mode & (0o077 if private else 0o022)
            or info.st_size > limit):
            raise ValueError('Archivo no confiable')
        if content:
            return source.read(limit + 1)
        return hashlib.file_digest(source, 'sha256').hexdigest()


def validate(plan):
    if not isinstance(plan, dict) or set(plan) != FIELDS or type(plan['schema_version']) is not int or plan['schema_version'] != 1:
        raise ValueError('Plan desconocido')
    for name in FIELDS - {'schema_version', 'cluster_uuid'}:
        if not isinstance(plan[name], str) or not re.fullmatch('[a-f0-9]{64}', plan[name]):
            raise ValueError('SHA inválido')
    if not isinstance(plan['cluster_uuid'], str) or str(UUID(plan['cluster_uuid'])) != plan['cluster_uuid']:
        raise ValueError('UUID inválido')


def registry_value(plan):
    validate(plan)
    return {KEY: {'product': 'linux', 'cluster_uuid': plan['cluster_uuid'], 'nodes': ['proxmox'],
        'definition_sha256': plan['definition_sha256'], 'bundle_sha256': plan['bundle_sha256'],
        'bundle_path': '/opt/nap/recipes/nap009-linux-1.0.0-'+plan['bundle_sha256']+'.tar.gz',
        'network_profile_ids': ['lab-vmnet8'],
        'networks': {'lab-vmnet8': {'subnets': ['172.16.36.0/24']}}}}


def install(plan, *, root=Path('/'), apply=False):
    desired = (json.dumps(registry_value(plan), sort_keys=True, separators=(',', ':'))+'\n').encode()
    registry = root/'etc/nap/runner/registry.json'
    bundle = root/('opt/nap/recipes/nap009-linux-1.0.0-'+plan['bundle_sha256']+'.tar.gz')
    image = root/'var/lib/vz/template/cache/nap009-linux-1.0.0.tar.gz'
    if checked(bundle, limit=2*1024**2) != plan['bundle_sha256'] or checked(image, limit=512*1024**2) != plan['image_sha256']:
        raise ValueError('Artefactos distintos a los revisados')

    def inspect():
        current = checked(registry, limit=65536, private=True, content=True)
        existing = current == desired
        if not existing and (hashlib.sha256(current).hexdigest() != plan['previous_sha256'] or json.loads(current) != {}):
            raise ValueError('El registro cambió; no se reemplazó ni adoptó')
        return current, existing

    current, existing = inspect()
    report = {'estado': 'plan_sin_cambios', 'entry_key': KEY, 'ya_existia': existing,
        'registry_sha256': hashlib.sha256(desired).hexdigest(), 'definition_sha256': plan['definition_sha256'],
        'staging_no_publicacion': True, 'invitados_no_creados': True}
    if not apply:
        return report
    lock = registry.parent/'registry.json.lock'
    fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    with os.fdopen(fd, 'r+') as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077 or info.st_nlink != 1:
            raise ValueError('Lock no confiable')
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        current, existing = inspect()
        report.update(estado='linux_staging_registrado', ya_existia=existing)
        if existing:
            return report
        backup_dir = Path(tempfile.mkdtemp(prefix='nap009-registro-respaldo-', dir=root/'root'))
        backup_dir.chmod(0o700)
        backup = backup_dir/'registry.json'
        backup_fd = os.open(backup, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(backup_fd, 'wb') as saved:
            saved.write(current); saved.flush(); os.fsync(saved.fileno())
        fd, temporary = tempfile.mkstemp(prefix='.nap009-registry-', dir=registry.parent)
        try:
            with os.fdopen(fd, 'wb') as output:
                os.fchmod(output.fileno(), 0o600)
                output.write(desired); output.flush(); os.fsync(output.fileno())
            # Revalidación bajo el lock inmediatamente antes de la sustitución.
            if inspect()[0] != current:
                raise ValueError('El registro cambió durante la preparación')
            os.replace(temporary, registry)
            directory_fd = os.open(registry.parent, os.O_DIRECTORY)
            try: os.fsync(directory_fd)
            finally: os.close(directory_fd)
            if checked(registry, limit=65536, private=True, content=True) != desired:
                raise ValueError('Registro no confirmado; conservar respaldo y revisar')
        finally:
            Path(temporary).unlink(missing_ok=True)
        report['respaldo_root'] = str(backup)
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan-b64', required=True)
    parser.add_argument('--plan-sha256', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if os.geteuid() != 0 or not Path('/etc/pve').is_dir():
        parser.error('Ejecutar sólo como root en el nodo PVE')
    try:
        if len(args.plan_b64) > 4096:
            raise ValueError('Plan demasiado grande')
        raw = base64.b64decode(args.plan_b64, validate=True)
        if hashlib.sha256(raw).hexdigest() != args.plan_sha256:
            raise ValueError('Plan diferente al revisado')
        report = install(json.loads(raw), apply=args.apply)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    except Exception as error:
        print('Registro no confirmado: '+type(error).__name__+'. Conservar respaldo root y revisar antes de repetir.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
