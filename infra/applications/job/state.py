"""Private durable manifests; anchored directories, atomic replace and short locks.

There is deliberately no delete-job operation. A terminal manifest is the replay
tombstone even after console text has been acknowledged and removed.
"""
from contextlib import contextmanager
import errno
import fcntl
from hashlib import sha256
import os
from pathlib import Path
import re
import stat
from uuid import UUID, uuid4

from .protocol import (JobError, IDENTITY_FIELDS, PROTOCOL, canonical, fingerprint,
                       parse_request, parse_response, strict_json, _timestamp)


MANIFEST_KEYS = frozenset({'schema_version', 'identity', 'configuracion', 'secreto_referencias',
    'fingerprint', 'controller_generation', 'node_boot_id', 'unit_invocation_id', 'dispatch_state',
    'credentials_loaded', 'worker_finished', 'estado', 'fase', 'last_source_seq', 'acknowledged_seq', 'resultado',
    'error_codigo', 'created_at', 'updated_at'})
PUBLIC_IDENTITY_KEYS = IDENTITY_FIELDS - {'protocol', 'lease_generation', 'nonce'} | {'nonce_sha256'}
STATUS_KEYS = ('estado', 'fase', 'fingerprint', 'node_boot_id', 'last_source_seq',
               'acknowledged_seq', 'resultado', 'error_codigo')
MAX_MANIFEST_BYTES = 131072


def uuid_text(value):
    try:
        if type(value) is not str or str(UUID(value)) != value: raise ValueError()
        return value
    except (ValueError, TypeError, AttributeError):
        raise JobError('INVALID_REQUEST') from None


def validate_manifest(job):
    """Validate public content and its fingerprint without loading any secret."""
    try:
        if type(job) is not dict or set(job) != MANIFEST_KEYS or job['schema_version'] != 'nap-job-state/1': raise ValueError()
        identity = job['identity']
        if type(identity) is not dict or set(identity) != PUBLIC_IDENTITY_KEYS: raise ValueError()
        if type(identity['nonce_sha256']) is not str or not re.fullmatch(r'[a-f0-9]{64}', identity['nonce_sha256']): raise ValueError()
        # A dummy private proof validates the request's structure. The real proof
        # is represented only by nonce_sha256 and checked on every controller call.
        synthetic = {k: v for k, v in identity.items() if k != 'nonce_sha256'}
        synthetic.update(protocol=PROTOCOL, action='start', nonce='0'*64,
            lease_generation=job['controller_generation'], configuracion=job['configuracion'],
            secreto_referencias=job['secreto_referencias'],
            secretos={s['nombre']: 'validation-placeholder' for s in job['configuracion']['secretos']})
        parse_request(canonical(synthetic))
        public = {**identity, 'protocol': PROTOCOL, 'configuracion': job['configuracion'],
                  'secreto_referencias': job['secreto_referencias']}
        if fingerprint(public) != job['fingerprint']: raise ValueError()
        if job['dispatch_state'] not in {'guardado', 'solicitado', 'observado'} or type(job['credentials_loaded']) is not bool: raise ValueError()
        if type(job['worker_finished']) is not bool: raise ValueError()
        if job['worker_finished'] and job['estado'] not in {'confirmado', 'fallido', 'incierto'}: raise ValueError()
        if job['unit_invocation_id'] is not None: uuid_text(job['unit_invocation_id'])
        _timestamp(job['created_at']); _timestamp(job['updated_at'])
        data = {**identity, 'lease_generation': job['controller_generation'], **{k: job[k] for k in STATUS_KEYS}}
        data['nonce_sha256'] = sha256(synthetic['nonce'].encode()).hexdigest()
        request = {k: v for k, v in synthetic.items() if k not in {'configuracion', 'secreto_referencias', 'secretos'}}
        request['action'] = 'status'
        parse_response(canonical({'protocol': PROTOCOL, 'ok': True, 'action': 'status', 'data': data}), request=request)
        if job['estado'] == 'confirmado' and (job['resultado'] is None or not job['resultado']['recurso_configurado'] or not job['worker_finished']): raise ValueError()
        if job['estado'] == 'fallido' and job['error_codigo'] is None: raise ValueError()
        return job
    except (JobError, ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        raise JobError('UNCONFIRMED') from None


def _os_error(exc):
    return JobError('NO_SPACE' if exc.errno in {errno.ENOSPC, errno.EDQUOT} else 'UNCONFIRMED')


class PrivateDirectory:
    """All file operations stay relative to a verified directory descriptor."""
    def __init__(self, path, *, create=True):
        self.path = Path(path)
        self.fd = None
        if not self.path.is_absolute() or '..' in self.path.parts: raise JobError('UNCONFIRMED')
        descriptor = None
        try:
            descriptor = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            parts = self.path.parts[1:]
            if not parts: raise JobError('UNCONFIRMED')
            for index, part in enumerate(parts):
                try:
                    child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
                except FileNotFoundError:
                    if not create or index != len(parts)-1: raise
                    try: os.mkdir(part, mode=0o700, dir_fd=descriptor)
                    except FileExistsError: pass
                    child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
                os.close(descriptor); descriptor = child
                info = os.fstat(descriptor)
                if info.st_uid not in {0, os.geteuid()}: raise JobError('UNCONFIRMED')
                if info.st_mode & 0o022 and not (info.st_uid == 0 and info.st_mode & stat.S_ISVTX): raise JobError('UNCONFIRMED')
            if os.fstat(descriptor).st_mode & 0o077: raise JobError('UNCONFIRMED')
            self.fd = descriptor; descriptor = None
        except OSError as exc:
            raise _os_error(exc) from None
        finally:
            if descriptor is not None: os.close(descriptor)

    def close(self):
        if self.fd is not None: os.close(self.fd); self.fd = None

    def __enter__(self): return self
    def __exit__(self, *args): self.close()

    def _open(self):
        if self.fd is None: raise JobError('UNCONFIRMED')

    @staticmethod
    def name(kind, identifier):
        if kind not in {'job', 'resource', 'credential'}: raise JobError('INVALID_REQUEST')
        return kind + '.' + uuid_text(identifier) + '.json'

    @staticmethod
    def _private_file(info):
        if (not stat.S_ISREG(info.st_mode) or info.st_uid not in {0, os.geteuid()}
                or info.st_mode & 0o077 or info.st_nlink != 1): raise JobError('UNCONFIRMED')

    def read(self, kind, identifier, *, limit=MAX_MANIFEST_BYTES):
        self._open()
        name = self.name(kind, identifier)
        try:
            descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.fd)
            with os.fdopen(descriptor, 'rb') as source:
                info = os.fstat(source.fileno()); self._private_file(info)
                if info.st_size > limit: raise JobError('UNCONFIRMED')
                raw = source.read(limit+1)
            return strict_json(raw, limit=limit)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise _os_error(exc) from None
        except JobError:
            raise JobError('UNCONFIRMED') from None

    def write(self, kind, identifier, value, *, limit=MAX_MANIFEST_BYTES):
        self._open()
        name = self.name(kind, identifier)
        try:
            raw = canonical(value)
            if len(raw) > limit: raise JobError('UNCONFIRMED')
            # Refuse links or unknown modes instead of overwriting someone else's file.
            try: self._private_file(os.stat(name, dir_fd=self.fd, follow_symlinks=False))
            except FileNotFoundError: pass
            temporary = '.tmp.' + uuid4().hex
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
            try:
                with os.fdopen(descriptor, 'wb') as target:
                    target.write(raw); target.flush(); os.fsync(target.fileno())
                os.replace(temporary, name, src_dir_fd=self.fd, dst_dir_fd=self.fd)
                os.fsync(self.fd)
            finally:
                try: os.unlink(temporary, dir_fd=self.fd)
                except FileNotFoundError: pass
        except OSError as exc:
            raise _os_error(exc) from None
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise JobError('UNCONFIRMED') from None


class StateStore(PrivateDirectory):
    """Callers hold node/resource locks only around short durable transitions."""
    @contextmanager
    def lock(self, kind, identifier=None):
        self._open()
        if kind == 'node' and identifier is None: name = 'lock.node'
        elif kind == 'resource': name = 'lock.resource.' + uuid_text(identifier)
        else: raise JobError('INVALID_REQUEST')
        descriptor = None
        try:
            descriptor = os.open(name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=self.fd)
            self._private_file(os.fstat(descriptor))
            try: fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError: raise JobError('UNCONFIRMED') from None
            yield
        except OSError as exc:
            raise _os_error(exc) from None
        finally:
            if descriptor is not None: os.close(descriptor)

    def read_job(self, execution_id):
        job = self.read('job', execution_id)
        if job is not None:
            validate_manifest(job)
            if job['identity']['execution_id'] != execution_id: raise JobError('UNCONFIRMED')
        return job

    def write_job(self, job):
        validate_manifest(job)
        self.write('job', job['identity']['execution_id'], job)

    def jobs(self):
        self._open()
        try:
            names = os.listdir(self.fd)
        except OSError as exc: raise _os_error(exc) from None
        result = []
        for name in sorted(names):
            if name.startswith('job.') and name.endswith('.json'):
                job = self.read_job(uuid_text(name[4:-5]))
                if job is None: raise JobError('UNCONFIRMED')
                result.append(job)
        return result
