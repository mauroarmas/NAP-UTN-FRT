"""Construcción offline de artefactos; los ensayos reales son un paso separado."""
from copy import deepcopy
from contextlib import contextmanager
from datetime import datetime, timezone
import gzip
import hashlib
import io
import stat
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import tarfile
import tempfile
import subprocess
from uuid import UUID

from app.schemas.definicion import validar_manifest
from app.schemas.evidencia import canonical, parse_document
from infra.services.sanitize import ImageError, MARKER, confined, workspace_root

BASE_CHECKS = {'image_digest', 'sanitized_image', 'repeatable_deployment', 'bootstrap_idempotence',
    'functional_access', 'student_network_access', 'persistence_after_restart', 'cross_instance_isolation'}


def file_sha256(path):
    checksum = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            checksum.update(chunk)
    return checksum.hexdigest()


def _relative(name):
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or len(name) > 4096 or any(ord(c) < 32 for c in name):
        raise ImageError('El archivo contiene una ruta inválida')
    return str(path)


def _link(name, target, *, hard=False):
    if len(target) > 4096 or any(ord(c) < 32 for c in target):
        raise ImageError('Enlace inválido')
    if target.startswith('/'):
        destination = posixpath.normpath(target.lstrip('/'))
    else:
        destination = posixpath.normpath(target if hard else posixpath.join(posixpath.dirname(name), target))
    if destination == '..' or destination.startswith('../'):
        raise ImageError('El enlace sale del rootfs')
    return destination if hard else posixpath.relpath(destination, posixpath.dirname(name) or '.')


def safe_extract(archive, destination, *, expected_sha256):
    archive, destination = Path(archive), Path(destination).absolute()
    if not re.fullmatch(r'[a-f0-9]{64}', expected_sha256):
        raise ImageError('El SHA-256 de la base no es válido')
    if (destination.exists() or destination.is_symlink() or not destination.parent.is_dir()
        or destination.parent.resolve() != destination.parent):
        raise ImageError('La extracción requiere un directorio nuevo y privado')
    try:
        fd = os.open(archive, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as original, tempfile.TemporaryFile(dir=destination.parent) as verified:
            info = os.fstat(original.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > 8 * 1024**3:
                raise ImageError('La base debe ser un archivo regular acotado')
            checksum = hashlib.sha256()
            for chunk in iter(lambda: original.read(1024 * 1024), b''):
                checksum.update(chunk); verified.write(chunk)
            if checksum.hexdigest() != expected_sha256:
                raise ImageError('El SHA-256 de la base no coincide')
            verified.seek(0)
            destination.mkdir(mode=0o700)
            with tarfile.open(fileobj=verified, mode='r:*') as source:
                entries, seen, size = [], set(), 0
                for original_entry in source:
                    name = _relative(original_entry.name)
                    if name == '.':
                        continue
                    if name in seen or name == '.nap-build-workspace' or len(entries) >= 200000:
                        raise ImageError('Entradas duplicadas o excesivas')
                    if not (original_entry.isfile() or original_entry.isdir() or original_entry.issym() or original_entry.islnk()):
                        raise ImageError('La base contiene un archivo especial')
                    if not 0 <= original_entry.uid <= 65535 or not 0 <= original_entry.gid <= 65535:
                        raise ImageError('Propietario no compatible con LXC no privilegiado')
                    size += original_entry.size
                    if original_entry.size < 0 or size > 64 * 1024**3:
                        raise ImageError('La base supera el tamaño permitido')
                    entry = original_entry.replace(name=name, deep=True)
                    if entry.issym() or entry.islnk():
                        entry.linkname = _link(name, entry.linkname, hard=entry.islnk())
                    entries.append(entry); seen.add(name)
                def closed_filter(member, directory):
                    filtered = tarfile.data_filter(member, directory)
                    # Conservar permisos Unix de una base cuyo contenido exacto
                    # acaba de comprobarse sobre esta misma copia privada.
                    return filtered.replace(uid=member.uid, gid=member.gid,
                        mode=(member.mode & 0o7777) if not member.issym() else None)
                source.extractall(destination, members=entries, filter=closed_filter)
            (destination / '.nap-build-workspace').write_text(MARKER)
    except (tarfile.TarError, ValueError, OSError, RuntimeError):
        raise ImageError('No se pudo extraer la base de forma segura') from None
    return destination


def archive_rootfs(root, output, *, source_date_epoch):
    root = workspace_root(root)
    output = Path(output).absolute()
    if output.is_relative_to(root) or type(source_date_epoch) is not int or source_date_epoch < 0:
        raise ImageError('Salida o fecha de construcción inválidas')
    try:
        with output.open('xb') as raw, gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode='w', format=tarfile.PAX_FORMAT) as archive:
                for parent, dirs, files in os.walk(root, followlinks=False):
                    dirs.sort(); files.sort()
                    for name in sorted(dirs + files):
                        path = Path(parent) / name
                        relative = path.relative_to(root).as_posix()
                        if relative == '.nap-build-workspace':
                            continue
                        item = archive.gettarinfo(str(path), arcname=relative)
                        if not (item.isfile() or item.isdir() or item.issym() or item.islnk()):
                            raise ImageError('El rootfs contiene un archivo especial')
                        if path.is_mount():
                            raise ImageError('No empaquetar sistemas de archivos montados')
                        item.mtime = source_date_epoch
                        item.uname = item.gname = ''
                        item.pax_headers = {}
                        if item.issym() or item.islnk():
                            item.linkname = _link(relative, item.linkname, hard=item.islnk())
                        if item.isfile():
                            with path.open('rb') as content:
                                archive.addfile(item, content)
                        else:
                            archive.addfile(item)
        return file_sha256(output)
    except (OSError, tarfile.TarError):
        raise ImageError('No se pudo empaquetar el rootfs') from None


def inspect_rootfs(root):
    root = workspace_root(root)
    try:
        release = confined(root, 'etc/os-release')
        if release.is_symlink():
            release = confined(root, 'usr/lib/os-release', regular=True)
        values = {}
        for line in release.read_text().splitlines():
            if '=' in line and not line.startswith('#'):
                key, value = line.split('=', 1)
                values[key] = value.strip().strip('"\'')
        if values.get('ID') != 'ubuntu' or values.get('VERSION_ID') != '24.04':
            raise ValueError()
        status = confined(root, 'var/lib/dpkg/status', regular=True).read_text()
        inventory = []
        for paragraph in status.split('\n\n'):
            fields = dict(line.split(': ', 1) for line in paragraph.splitlines() if ': ' in line and not line.startswith(' '))
            if fields.get('Status') != 'install ok installed':
                continue
            name, version, arch = fields['Package'], fields['Version'], fields['Architecture']
            if (not re.fullmatch(r'[a-z0-9][a-z0-9+.-]{0,99}', name)
                or not re.fullmatch(r'[0-9][A-Za-z0-9.+:~_-]{0,119}', version) or arch not in {'amd64', 'all'}):
                raise ValueError()
            inventory.append({'name': name, 'version': version, 'architecture': arch})
        if not inventory or not any(item['architecture'] == 'amd64' for item in inventory):
            raise ValueError()
        if len({item['name'] for item in inventory}) != len(inventory):
            raise ValueError()
        return sorted(inventory, key=lambda item: item['name'])
    except (OSError, KeyError, ValueError):
        raise ImageError('La base no es Ubuntu 24.04 amd64 con inventario exacto') from None


def evidence_from_trials(trials, *, definition_id, manifest, operator, reference, cluster_uuid, pve_versions, environment):
    try:
        UUID(definition_id); UUID(cluster_uuid)
        validar_manifest(manifest, parcial=True)
        required = BASE_CHECKS | ({'unique_secrets'} if manifest['product'] != 'linux' else set())
        if manifest['product'] == 'bookstack':
            required.add('reader_permissions_and_revocation')
        if not isinstance(trials, list) or len(trials) < 2:
            raise ValueError()
        identities, observations, checks = set(), [], None
        for trial in trials:
            if set(trial) != {'resource_uuid', 'image_sha256', 'recipe_sha256', 'entorno', 'observado_at', 'checks'}:
                raise ValueError()
            identity = str(UUID(trial['resource_uuid']))
            if identity in identities or trial['entorno'] != environment:
                raise ValueError()
            if trial['image_sha256'] != manifest['image']['sha256'] or trial['recipe_sha256'] != manifest['preparation']['bundle_sha256']:
                raise ValueError()
            if not required <= set(trial['checks']) or any(value is not True for value in trial['checks'].values()):
                raise ValueError()
            current = set(trial['checks'])
            checks = current if checks is None else checks & current
            observed = datetime.fromisoformat(trial['observado_at'].replace('Z', '+00:00'))
            if observed.tzinfo is None or observed > datetime.now(timezone.utc):
                raise ValueError()
            identities.add(identity); observations.append(observed)
        proof = {'schema_version': 1, 'tipo': 'validacion_definicion', 'entorno': environment,
            'operador_institucional': operator, 'referencia_institucional': reference,
            'observado_at': max(observations).astimezone(timezone.utc).isoformat().replace('+00:00', 'Z'),
            'resultado': {'definicion_id': definition_id, 'definition_key': manifest['definition_key'],
                'definition_version': manifest['definition_version'], 'image_sha256': manifest['image']['sha256'],
                'recipe_sha256': manifest['preparation']['bundle_sha256'], 'cluster_uuid': cluster_uuid,
                'pve_versions': pve_versions, 'instancias': sorted(identities), 'checks': sorted(checks)}}
        parse_document(canonical(proof).encode())
        return proof
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
        raise ImageError('Faltan dos ensayos distintos satisfactorios y concordantes') from None


def finalize_manifest(draft, evidence, *, reference, checksum):
    try:
        UUID(reference)
        parse_document(canonical(evidence).encode())
        if evidence['tipo'] != 'validacion_definicion' or hashlib.sha256(canonical(evidence).encode()).hexdigest() != checksum:
            raise ValueError()
        result = evidence['resultado']
        if (result['definition_key'] != draft['definition_key'] or result['definition_version'] != draft['definition_version']
            or result['image_sha256'] != draft['image']['sha256'] or result['recipe_sha256'] != draft['preparation']['bundle_sha256']):
            raise ValueError()
        complete = deepcopy(draft)
        complete['validation'] = {'result': 'passed', 'validated_at': evidence['observado_at'],
            'evidence_id': reference, 'evidence_sha256': checksum, 'cluster_uuid': result['cluster_uuid'],
            'pve_versions': result['pve_versions'], 'instances_tested': len(result['instancias']), 'checks': result['checks']}
        validar_manifest(complete)
        return complete
    except (ValueError, TypeError, KeyError):
        raise ImageError('El registro de evidencia no coincide con el artefacto') from None


SOURCE_ROOT = Path(__file__).resolve().parents[2]


def _recipe_files(product):
    files = [SOURCE_ROOT / 'infra/services/common.py', SOURCE_ROOT / f'infra/services/{product}/bootstrap.py']
    if product == 'bookstack':
        files.append(SOURCE_ROOT / 'infra/services/bookstack/configure.php')
    return files


def verify_recipe_revision(revision, product):
    files = _recipe_files(product) + [Path(__file__).resolve(), Path(__file__).with_name('sanitize.py'),
        SOURCE_ROOT / f'infra/services/{product}/build.sh']
    try:
        for path in files:
            data = subprocess.run(['/usr/bin/git', '-c', f'safe.directory={SOURCE_ROOT}', '-C', str(SOURCE_ROOT),
                'cat-file', 'blob', revision + ':' + path.relative_to(SOURCE_ROOT).as_posix()],
                check=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10,
                env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'}).stdout
            if path.is_symlink() or data != path.read_bytes():
                raise ValueError()
    except (OSError, ValueError, subprocess.SubprocessError):
        raise ImageError('La receta debe coincidir con una revisión Git íntegra y comprometida') from None


def make_recipe_bundle(product, output):
    with Path(output).open('xb') as raw, gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode='w', format=tarfile.PAX_FORMAT) as archive:
            for source in _recipe_files(product):
                if source.is_symlink() or not source.is_file():
                    raise ImageError('La receta fija no está disponible')
                data = source.read_bytes()
                item = tarfile.TarInfo(source.name)
                item.size, item.mode, item.mtime = len(data), 0o500, 0
                archive.addfile(item, io.BytesIO(data))


@contextmanager
def resolver_for_build(root, *, contents=None):
    """DNS del host solo en el chroot de build; restaurar el enlace guest."""
    from infra.services.sanitize import _write
    root = workspace_root(root)
    path = confined(root, 'etc/resolv.conf')
    contents = Path('/etc/resolv.conf').read_bytes() if contents is None else contents
    if not contents or len(contents) > 65536 or b'\x00' in contents:
        raise ImageError('No hay un resolver válido para el host de build')
    original_link, original, mode = None, None, None
    if path.is_symlink():
        original_link = os.readlink(path)
    elif path.exists():
        if not path.is_file():
            raise ImageError('Resolver guest inválido')
        original, mode = path.read_bytes(), stat.S_IMODE(path.stat().st_mode)
    path.unlink(missing_ok=True)
    try:
        _write(path, contents.decode(), 0o644)
        yield
    finally:
        path.unlink(missing_ok=True)
        if original_link is not None:
            path.symlink_to(original_link)
        elif original is not None:
            path.write_bytes(original)
            path.chmod(mode)


def stage_package_cache(root, cache):
    """Copiar .deb como caché; APT verifica sus hashes con los índices firmados."""
    import shutil
    root = workspace_root(root)
    cache = Path(cache).absolute()
    if cache.is_symlink() or cache.resolve() != cache or not cache.is_dir():
        raise ImageError('La caché requiere un directorio regular del host de build')
    entries = sorted(cache.glob('*.deb'))
    if len(entries) > 5000:
        raise ImageError('La caché supera el tamaño permitido')
    target = confined(root, 'var/cache/apt/archives')
    if target.is_symlink() or (target.exists() and not target.is_dir()):
        raise ImageError('Destino de caché no seguro')
    target.mkdir(parents=True, exist_ok=True)
    total = 0
    try:
        for path in entries:
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.+%:~_-]{0,240}\.deb', path.name):
                raise ImageError('Nombre de caché no permitido')
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, 'rb') as source:
                info = os.fstat(source.fileno())
                total += info.st_size
                if not stat.S_ISREG(info.st_mode) or info.st_size > 512 * 1024**2 or total > 8 * 1024**3:
                    raise ImageError('La caché contiene archivos no regulares o excesivos')
                with (target / path.name).open('xb') as output:
                    shutil.copyfileobj(source, output, length=1024*1024)
    except OSError:
        raise ImageError('No se pudo copiar la caché privada de paquetes') from None


def install_product(root, plan, *, apt_cache=None):
    """Solo CLI del operador en host de build; nunca se invoca desde la API."""
    import shutil
    from infra.services.sanitize import _write
    if os.geteuid() != 0:
        raise ImageError('La construcción requiere el host de build y permisos de root')
    root = workspace_root(root)
    if apt_cache is not None:
        stage_package_cache(root, apt_cache)
    stage = confined(root, 'opt/nap-build')
    stage.mkdir(parents=True, mode=0o700)
    product = plan['manifest']['product']
    script = SOURCE_ROOT / f'infra/services/{product}/build.sh'
    if script.is_symlink() or not script.is_file():
        raise ImageError('Falta la receta de construcción del producto')
    _write(confined(root, 'usr/sbin/policy-rc.d'), '#!/bin/sh\nexit 101\n', 0o755)
    (stage / 'plan.json').write_text(canonical(plan))
    shutil.copyfile(script, stage / 'build.sh')
    for source in _recipe_files(product):
        shutil.copyfile(source, stage / source.name)
    devices = []
    try:
        for name, minor in [('null', 3), ('zero', 5), ('random', 8), ('urandom', 9)]:
            path = confined(root, 'dev/' + name)
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() or path.is_symlink():
                raise ImageError('El rootfs base contiene dispositivos o enlaces inesperados')
            os.mknod(path, 0o666 | stat.S_IFCHR, os.makedev(1, minor))
            devices.append(path)
        base = ['/usr/sbin/chroot', str(root), '/usr/bin/env', '-i', 'PATH=/usr/sbin:/usr/bin:/sbin:/bin',
            'LANG=C.UTF-8', 'DEBIAN_FRONTEND=noninteractive']
        commands = [base + ['/usr/bin/apt-get', '-o', 'Acquire::Languages=none', 'update'],
            base + ['/usr/bin/apt-get', 'install', '--yes', '--no-install-recommends']
                + [name + '=' + version for name, version in sorted(plan['package_lock'].items())],
            base + ['/bin/bash', '/opt/nap-build/build.sh']]
        with resolver_for_build(root):
            for command in commands:
                subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=1800, env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C.UTF-8'})
    except (OSError, subprocess.SubprocessError):
        raise ImageError('Falló la instalación fijada; no se generó una imagen validada') from None
    finally:
        for device in devices:
            device.unlink(missing_ok=True)
        shutil.rmtree(stage)
        confined(root, 'usr/sbin/policy-rc.d').unlink(missing_ok=True)


def build_artifact(plan, base_archive, output_dir, *, installer=None, bundle_factory=None, revision_verifier=None, apt_cache=None):
    from infra.services.sanitize import sanitize_rootfs, _write
    from fastapi import HTTPException
    try:
        if set(plan) != {'schema_version', 'definition_id', 'base_sha256', 'source_date_epoch', 'package_lock', 'manifest'}:
            raise ValueError()
        UUID(plan['definition_id'])
        if type(plan['schema_version']) is not int or plan['schema_version'] != 1:
            raise ValueError()
        value = deepcopy(plan['manifest'])
        if 'validation' in value:
            raise ValueError()
        validar_manifest(value, parcial=True)
        product = value['product']
        if product not in {'linux', 'postgresql', 'bookstack'} or not value['image']['volume_id'].endswith('.tar.gz'):
            raise ValueError()
        revision = value['preparation']['recipe_revision']
        if not re.fullmatch(r'[a-f0-9]{40}', revision) or not re.fullmatch(r'[a-f0-9]{64}', plan['base_sha256']):
            raise ValueError()
        lock = plan['package_lock']
        if not isinstance(lock, dict) or not lock or any(not re.fullmatch(r'[a-z0-9][a-z0-9+.-]{0,99}', name)
            or not isinstance(version, str) or not re.fullmatch(r'[0-9][A-Za-z0-9.+:~_-]{0,119}', version) for name, version in lock.items()):
            raise ValueError()
        if type(plan['source_date_epoch']) is not int or plan['source_date_epoch'] < 0:
            raise ValueError()
        (revision_verifier or verify_recipe_revision)(revision, product)
        output_dir = Path(output_dir).absolute()
        if output_dir.exists() or output_dir.is_symlink() or output_dir.parent.resolve() != output_dir.parent:
            raise ValueError()
        output_dir.mkdir(mode=0o700)
        bundle = output_dir / 'recipe.tar.gz'
        (bundle_factory or make_recipe_bundle)(product, bundle)
        value['preparation']['bundle_sha256'] = file_sha256(bundle)
        with tempfile.TemporaryDirectory(prefix='nap-build-') as workspace:
            root = safe_extract(base_archive, Path(workspace) / 'rootfs', expected_sha256=plan['base_sha256'])
            inspect_rootfs(root)
            if installer is not None:
                installer(root, plan)
            else:
                install_product(root, plan, apt_cache=apt_cache)
            inventory = inspect_rootfs(root)
            if {item['name']: item['version'] for item in inventory} != lock:
                raise ImageError('El inventario instalado no coincide con el lock completo')
            sanitize_rootfs(root, product)
            _write(confined(root, 'etc/nap/image.json'), canonical({'protocol': 'nap-image/1',
                'product': product, 'definition_key': value['definition_key'], 'definition_version': value['definition_version'],
                'recipe_revision': revision, 'bundle_sha256': value['preparation']['bundle_sha256'], 'base_sha256': plan['base_sha256']}), 0o444)
            image = output_dir / value['image']['volume_id'].split('/')[-1]
            value['image']['sha256'] = archive_rootfs(root, image, source_date_epoch=plan['source_date_epoch'])
            value['runtime']['packages'] = inventory
        validar_manifest(value, parcial=True)
        manifest_path = output_dir / 'manifest-draft.json'
        manifest_path.write_text(canonical(value) + '\n')
        for artifact in [image, bundle, manifest_path]:
            artifact.chmod(0o444)
        return {'manifest': value, 'manifest_path': str(manifest_path), 'image_path': str(image), 'bundle_path': str(bundle)}
    except (KeyError, TypeError, ValueError, OSError, HTTPException):
        raise ImageError('Plan, lock, revisión o archivos de construcción inválidos') from None


def main(argv=None):
    import argparse
    from fastapi import HTTPException
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    build = commands.add_parser('build', help='Construir una copia privada con versiones fijadas')
    build.add_argument('--plan', required=True, type=Path)
    build.add_argument('--base', required=True, type=Path)
    build.add_argument('--output', required=True, type=Path)
    build.add_argument('--apt-cache', type=Path, help='Caché opcional .deb montada solo lectura; APT verifica sus hashes')
    build.add_argument('--execute', action='store_true', help='Autoriza instalación en el host de build')
    evidence = commands.add_parser('evidence', help='Convertir ensayos comprobados en documento importable')
    for name in ['manifest', 'trials', 'output']:
        evidence.add_argument('--' + name, required=True, type=Path)
    for name in ['definition-id', 'operator', 'reference', 'cluster-uuid']:
        evidence.add_argument('--' + name, required=True)
    evidence.add_argument('--pve-version', action='append', required=True)
    evidence.add_argument('--environment', choices=['real', 'simulado'], required=True)
    finalize = commands.add_parser('finalize', help='Completar manifiesto con el UUID y checksum importados')
    for name in ['manifest', 'evidence', 'registration', 'output']:
        finalize.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args(argv)
    def read(path):
        def pairs(items):
            result = {}
            for key, value in items:
                if key in result:
                    raise ValueError()
                result[key] = value
            return result
        def reject_number(value):
            raise ValueError()
        with path.open('rb') as source:
            raw = source.read(262145)
        if len(raw) > 262144:
            raise ValueError()
        return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_float=reject_number, parse_constant=reject_number)
    try:
        if args.action == 'build':
            if not args.execute:
                raise ImageError('Usá --execute en el host de build después de revisar el plan')
            result = build_artifact(read(args.plan), args.base, args.output, apt_cache=args.apt_cache)
            print('Borrador construido: ' + result['manifest_path'])
            return
        if args.action == 'evidence':
            result = evidence_from_trials(read(args.trials), definition_id=args.definition_id, manifest=read(args.manifest),
                operator=args.operator, reference=args.reference, cluster_uuid=args.cluster_uuid,
                pve_versions=args.pve_version, environment=args.environment)
        else:
            registration = read(args.registration)
            result = finalize_manifest(read(args.manifest), read(args.evidence), reference=registration['evidencia_ref'], checksum=registration['sha256'])
        with args.output.open('x') as output:
            output.write(canonical(result) + '\n')
        args.output.chmod(0o600)
        print('Artefacto generado: ' + str(args.output))
    except (ImageError, ValueError, KeyError, TypeError, OSError, HTTPException) as exc:
        message = str(exc) if isinstance(exc, ImageError) else 'Entrada inválida; no se publicó ninguna definición'
        parser.exit(1, message + '\n')


if __name__ == '__main__':
    main()
