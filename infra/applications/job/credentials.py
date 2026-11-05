"""Ephemeral private source → systemd LoadCredential copy → durable claim → unlink.

Values are read only by the fixed worker. No command line, spool or result carries
them. The systemd copy remains private for the lifetime of that service.
"""
import hmac
import os
from pathlib import Path
import re

from .protocol import JobError, canonical, strict_json
from .state import PrivateDirectory, uuid_text, _os_error

MAX_CREDENTIAL_BYTES = 262144


def validate_payload(value, execution_id, fingerprint):
    try:
        if (type(fingerprint) is not str or not re.fullmatch(r'[a-f0-9]{64}', fingerprint)
                or type(value) is not dict or set(value) != {'schema_version', 'execution_id', 'fingerprint', 'secretos'}
                or value['schema_version'] != 'nap-job-credentials/1'
                or value['execution_id'] != uuid_text(execution_id) or value['fingerprint'] != fingerprint):
            raise ValueError()
        values = value['secretos']
        if type(values) is not dict or len(values) > 20: raise ValueError()
        for name, secret in values.items():
            if (type(name) is not str or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,63}', name)
                    or type(secret) is not str or not secret or '\x00' in secret or len(secret.encode('utf-8')) > 4096):
                raise ValueError()
        if len(canonical(value)) > MAX_CREDENTIAL_BYTES: raise ValueError()
        return value
    except (ValueError, KeyError, TypeError, UnicodeError, RecursionError):
        raise JobError('INVALID_REQUEST') from None


class CredentialChannel(PrivateDirectory):
    def __init__(self, *, source_root=Path('/run/nap-application-jobs'), credentials_root=Path('/run/credentials'), create=True):
        super().__init__(source_root, create=create)
        self.credentials_root = Path(credentials_root)
        if not self.credentials_root.is_absolute() or '..' in self.credentials_root.parts:
            self.close(); raise JobError('UNCONFIRMED')

    def stage(self, execution_id, *, fingerprint, secretos):
        payload = validate_payload({'schema_version': 'nap-job-credentials/1', 'execution_id': execution_id,
            'fingerprint': fingerprint, 'secretos': secretos}, execution_id, fingerprint)
        existing = self.read('credential', execution_id, limit=MAX_CREDENTIAL_BYTES)
        if existing is not None:
            # A replay does not overwrite values; compare privately without storing hashes.
            if not hmac.compare_digest(canonical(existing), canonical(payload)):
                raise JobError('EXECUTION_CONFLICT')
            return
        self.write('credential', execution_id, payload, limit=MAX_CREDENTIAL_BYTES)

    def discard(self, execution_id, *, fingerprint=None):
        self._open()
        existing = self.read('credential', execution_id, limit=MAX_CREDENTIAL_BYTES)
        if existing is None: return
        # Only the owning job can retire an existing source, never an unknown file.
        if fingerprint is None: raise JobError('UNCONFIRMED')
        validate_payload(existing, execution_id, fingerprint)
        try:
            os.unlink(self.name('credential', execution_id), dir_fd=self.fd)
            os.fsync(self.fd)
        except FileNotFoundError:
            return  # Another authenticated observer retired the same loaded source.
        except OSError as exc:
            raise _os_error(exc) from None

    def load_and_retire(self, execution_id, *, fingerprint, mark_loaded):
        self._open(); uuid_text(execution_id)
        expected = self.credentials_root / ('nap-application-'+execution_id+'.service')
        if Path(os.environ.get('CREDENTIALS_DIRECTORY', '')) != expected: raise JobError('UNCONFIRMED')
        try:
            with PrivateDirectory(expected, create=False) as copy:
                descriptor = os.open('deployment', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=copy.fd)
                with os.fdopen(descriptor, 'rb') as source:
                    info = os.fstat(source.fileno()); copy._private_file(info)
                    if info.st_size > MAX_CREDENTIAL_BYTES: raise JobError('UNCONFIRMED')
                    payload = strict_json(source.read(MAX_CREDENTIAL_BYTES+1), limit=MAX_CREDENTIAL_BYTES)
            validate_payload(payload, execution_id, fingerprint)
            staged = self.read('credential', execution_id, limit=MAX_CREDENTIAL_BYTES)
            if staged is not None and not hmac.compare_digest(canonical(staged), canonical(payload)):
                raise JobError('EXECUTION_CONFLICT')
            claimed = mark_loaded()
            if type(claimed) is not bool: raise JobError('UNCONFIRMED')
            # The loaded proof is durable before deleting the original.
            self.discard(execution_id, fingerprint=fingerprint)
            return payload['secretos'] if claimed else None
        except OSError as exc:
            raise _os_error(exc) from None
