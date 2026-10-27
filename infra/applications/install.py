#!/usr/bin/env python3
"""Explicit root package installation. No accounts, SSH, pools or guests are changed."""
import argparse
from contextlib import contextmanager
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from uuid import uuid4, UUID


JOBS = ('protocol','configuration','state','supervisor','credentials','worker','runtime','collector','spool','redaction','selfcheck','network','tls','isolation')
SOURCES = {f'/opt/nap/applications/job/{name}.py': f'infra/applications/job/{name}.py' for name in JOBS}
SOURCES.update({f'/opt/nap/applications/docker/{name}.py':f'infra/applications/docker/{name}.py'
    for name in ('runtime','contract','guest','deploy','access','probes')})
SOURCES['/opt/nap/applications/profiles/docker/ubuntu24.json']='infra/applications/profiles/docker/ubuntu24.json'
SOURCES.update({
    '/opt/nap/applications/profiles/registry.py': 'infra/applications/profiles/registry.py',
    '/opt/nap/applications/profiles/profile_contract.py': 'backend/app/schemas/application_profiles.py',
    '/opt/nap/applications/schemas/nap-deployment-1.json': 'infra/applications/schemas/nap-deployment-1.json',
    '/opt/nap/runner/nap_guest_runner.py': 'infra/runner/nap_guest_runner.py',
    '/opt/nap/runner/node_executor.py': 'infra/runner/node_executor.py',
    '/opt/nap/runner/protocol.py': 'backend/app/schemas/guest_runner.py',
    '/opt/nap/runner/registry_entries.py': 'backend/app/utils/artifact_registry.py',
    '/usr/local/sbin/nap-guest-runner': 'infra/runner/nap-guest-runner',
})
TMPFILES = '/etc/tmpfiles.d/nap-application-jobs.conf'
CONFIG = '/etc/nap/applications-011/runner.json'
RECEIPT = '/etc/nap/applications-011/package.json'
GENERATED = {f'/opt/nap/applications/{name}__init__.py' for name in ('', 'job/', 'profiles/', 'docker/')}
ALLOWED = set(SOURCES) | GENERATED | {TMPFILES, '/opt/nap/applications/job/selfcheck.py'}


class PackageError(ValueError): pass


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def build_files(source_root):
    source_root = Path(source_root).absolute()
    files = {}
    for target, relative in SOURCES.items():
        path = source_root / relative
        info = path.lstat()
        if (path.parent.resolve() != path.parent or not stat.S_ISREG(info.st_mode) or info.st_mode & 0o002
                or info.st_uid not in {0, os.geteuid()} or info.st_size > 1048576): raise PackageError('UNTRUSTED_SOURCE')
        files[target] = (path.read_bytes(), 0o755 if target.endswith('/nap-guest-runner') else 0o444)
    files.update({name: (b'', 0o444) for name in GENERATED})
    files[TMPFILES] = (b'd /run/nap-application-jobs 0700 root root -\n', 0o644)
    return files


def read_safe(path, *, limit=2097152):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as source:
        info = os.fstat(source.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_mode & 0o022
                or info.st_uid not in {0, os.geteuid()} or info.st_size > limit): raise PackageError('UNTRUSTED_DESTINATION')
        value = source.read(limit+1)
    if len(value) > limit: raise PackageError('DESTINATION_TOO_LARGE')
    return value, stat.S_IMODE(info.st_mode)


def safe_directory(path, *, mode=0o755):
    if path.exists() or path.is_symlink():
        info = path.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid not in {0, os.geteuid()} or info.st_mode & 0o022):
            raise PackageError('UNTRUSTED_DIRECTORY')
    else:
        safe_directory(path.parent)
        path.mkdir(mode=mode)


def atomic_write(path, content, mode):
    descriptor, temporary = tempfile.mkstemp(prefix='.nap011-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as target:
            target.write(content); target.flush(); os.fchmod(target.fileno(), mode); os.fsync(target.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def _active_jobs(root):
    folder = root/'var/lib/nap-application-jobs'
    if not folder.exists(): return
    safe_directory(folder)
    for path in folder.glob('job.*.json'):
        try:
            value = json.loads(read_safe(path, limit=131072)[0])
            if __package__:
                from .job.state import validate_manifest
            else:
                # Explicit reviewed checkout, also used to construct the package.
                sys.path.insert(0,str(Path(__file__).absolute().parents[2]))
                from infra.applications.job.state import validate_manifest
            validate_manifest(value)
            if value.get('estado') not in {'confirmado', 'fallido'}: raise ValueError()
        except Exception: raise PackageError('ACTIVE_OR_UNKNOWN_JOB') from None


def _initial_config(value):
    try:
        if (type(value) is not dict or set(value) != {'schema_version', 'cluster_uuid','node','profiles'}
                or value['schema_version'] != 'nap-application-node/1' or value['profiles'] != {}
                or str(UUID(value['cluster_uuid'])) != value['cluster_uuid']
                or not __import__('re').fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,99}', value['node'])): raise ValueError()
        return value
    except Exception: raise PackageError('INVALID_INITIAL_CONFIGURATION') from None


@contextmanager
def upgrade_guard(root, *, apply):
    state=root/'var/lib/nap-application-jobs'
    descriptor=None
    try:
        if apply and (state.exists() or state.is_symlink()):
            safe_directory(state)
            descriptor=os.open(state/'lock.node',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_NONBLOCK,0o600)
            info=os.fstat(descriptor)
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_mode & 0o077
                    or info.st_uid not in {0,os.geteuid()}):raise PackageError('UNTRUSTED_LOCK')
            try:fcntl.flock(descriptor,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise PackageError('PACKAGE_ADMISSION_BUSY') from None
        yield
    finally:
        if descriptor is not None:os.close(descriptor)


def install_files(files, *, root=Path('/'), apply=False, previous=None, config=None, verify=None):
    root=Path(root).absolute()
    if root.resolve() != root: raise PackageError('UNTRUSTED_ROOT')
    if root == Path('/') and os.geteuid() != 0: raise PackageError('ROOT_REQUIRED')
    with upgrade_guard(root,apply=apply):
        return _install_files(files,root=root,apply=apply,previous=previous,config=config,verify=verify)


def _install_files(files, *, root, apply, previous, config, verify):
    root = Path(root).absolute()
    if root == Path('/') and os.geteuid() != 0: raise PackageError('ROOT_REQUIRED')
    if root.resolve() != root: raise PackageError('UNTRUSTED_ROOT')
    _active_jobs(root)
    previous = dict(previous or {})
    receipt_path = root/RECEIPT.lstrip('/')
    if receipt_path.exists() or receipt_path.is_symlink():
        try:
            receipt = json.loads(read_safe(receipt_path)[0])
            if receipt['schema_version'] != 'nap-application-package/1': raise ValueError()
            previous.update({k: v['sha256'] for k,v in receipt['files'].items()})
        except Exception: raise PackageError('UNTRUSTED_PACKAGE_RECEIPT') from None
    proposed = dict(files)
    if not proposed or not set(proposed) <= ALLOWED: raise PackageError('UNKNOWN_PACKAGE_PATH')
    if config is not None:
        _initial_config(config)
        path = root/CONFIG.lstrip('/')
        if path.exists() or path.is_symlink():
            try:
                current = json.loads(read_safe(path)[0])
                if (set(current) not in (set(config),set(config)|{'networks'})
                        or any(current[k] != config[k] for k in ('schema_version','cluster_uuid','node'))
                        or type(current['profiles']) is not dict or type(current.get('networks',{})) is not dict): raise ValueError()
            except Exception: raise PackageError('EXISTING_CONFIGURATION_DIFFERS') from None
        else: proposed[CONFIG] = (encode(config)+b'\n', 0o600)
    manifest = {name: {'sha256': sha256(data).hexdigest(), 'mode': mode} for name,(data,mode) in files.items()}
    receipt = {'schema_version': 'nap-application-package/1', 'files': manifest, 'code_sha256': sha256(encode(manifest)).hexdigest()}
    proposed[RECEIPT] = (encode(receipt)+b'\n', 0o600)
    changes = []
    # Validate every target before creating a directory or touching any old file.
    for name,(data,mode) in proposed.items():
        if type(data) is not bytes or len(data) > 1048576 or mode not in {0o444,0o600,0o644,0o755}: raise PackageError('INVALID_PACKAGE_FILE')
        path = root/name.lstrip('/')
        for parent in (path.parent, *path.parent.parents):
            if parent == root.parent: break
            if parent.exists() or parent.is_symlink():
                safe_directory(parent)
            if parent == root: break
        if path.parent.exists() and path.parent.resolve() != path.parent: raise PackageError('UNTRUSTED_DIRECTORY')
        old, old_mode = read_safe(path) if path.exists() or path.is_symlink() else (None, None)
        if old is not None and old != data and name != RECEIPT and sha256(old).hexdigest() != previous.get(name):
            raise PackageError('UNKNOWN_PREVIOUS_VERSION')
        if (old,old_mode) != (data,mode): changes.append((name,path,data,mode,old,old_mode))
    public = {'state': 'plan', 'changed_files': sum(n != RECEIPT for n,*_ in changes),
              'code_sha256': receipt['code_sha256'], 'profiles_enabled_by_install': [], 'guests_created': False}
    if not apply: return public
    backup = root/'root'/('nap011-package-backup-'+uuid4().hex)
    safe_directory(backup, mode=0o700)
    for _,path,_,_,old,old_mode in changes:
        if old is not None:
            target = backup/path.relative_to(root)
            safe_directory(target.parent)
            atomic_write(target, old, 0o600)
    applied = []
    try:
        for path in (root/'etc/nap/applications-011', root/'var/lib/nap-application-jobs', root/'run/nap-application-jobs', root/'var/lib/nap-application-tls', root/'var/lib/nap-application-isolation'):
            safe_directory(path, mode=0o700)
            if path.stat().st_mode & 0o077: raise PackageError('PRIVATE_DIRECTORY_REQUIRED')
        for item in changes:
            _,path,data,mode,_,_ = item
            safe_directory(path.parent)
            atomic_write(path,data,mode); applied.append(item)
        if verify is not None: verify()
    except Exception:
        for _,path,_,_,old,old_mode in reversed(applied):
            if old is None: path.unlink()
            else: atomic_write(path,old,old_mode)
        raise PackageError('INSTALL_ROLLED_BACK') from None
    return {**public, 'state': 'installed', 'backup': str(backup)}


def verify_installed():
    subprocess.run(['/usr/bin/python3','-I','-c',
        "import sys;sys.path.insert(0,'/opt/nap');from jsonschema import Draft202012Validator;from applications.job.worker import ApplicationWorker;from applications.profiles.registry import ProfileRegistry"],
        stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True,timeout=10)
    subprocess.run(['/usr/bin/systemd-tmpfiles','--create','/etc/tmpfiles.d/nap-application-jobs.conf'],
        stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True,timeout=10)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--previous', type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    try:
        config = json.loads(read_safe(args.config)[0]) if args.config else None
        previous = json.loads(read_safe(args.previous)[0]) if args.previous else None
        files = build_files(args.source_root)
        if args.apply:
            subprocess.run(['/usr/bin/python3','-I','-c','import jsonschema'], stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True,timeout=10)
        result = install_files(files, apply=args.apply, previous=previous, config=config,
                               verify=verify_installed if args.apply else None)
        print(json.dumps(result))
    except Exception as exc:
        code = str(exc) if isinstance(exc, PackageError) else 'PACKAGE_UNCONFIRMED'
        print(json.dumps({'state':'unconfirmed','code':code}))
        raise SystemExit(1) from None


if __name__ == '__main__': main()
