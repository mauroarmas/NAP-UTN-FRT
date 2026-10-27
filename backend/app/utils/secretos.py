"""Cifrado autenticado con claves externas y contexto de uso verificable."""

from copy import deepcopy
import json
import re

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


class SecretError(ValueError):
    pass


class Keyring:
    def __init__(self, keys, *, active):
        try:
            if active not in keys or not keys or any(not re.fullmatch(r'[A-Za-z0-9_-]{1,40}', key) for key in keys):
                raise ValueError()
            self._keys = {name: Fernet(value.encode()) for name, value in keys.items()}
            self.active = active
        except (ValueError, TypeError, AttributeError):
            raise SecretError('Keyring ausente o inválido') from None

    def encrypt(self, value, *, context):
        if not isinstance(context, str) or not 1 <= len(context) <= 200:
            raise SecretError('Contexto de secreto inválido')
        raw = json.dumps({'version': 1, 'context': context, 'value': value},
                         ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
        return 'v1:' + self.active + ':' + self._keys[self.active].encrypt(raw).decode()

    def decrypt(self, token, *, context):
        try:
            version, key_id, ciphertext = token.split(':', 2)
            if version != 'v1' or key_id not in self._keys or len(ciphertext) > 1_000_000:
                raise ValueError()
            envelope = json.loads(self._keys[key_id].decrypt(ciphertext.encode()))
            if envelope['version'] != 1 or envelope['context'] != context:
                raise ValueError()
            return envelope['value']
        except (ValueError, KeyError, TypeError, AttributeError, InvalidToken, UnicodeError):
            raise SecretError('No se pudo recuperar el secreto autorizado') from None

    def rotate(self, token, *, context):
        return self.encrypt(self.decrypt(token, context=context), context=context)


def configured_keyring(settings=None):
    settings = settings or get_settings()
    values = set(settings.secret_keyring.values())
    if not settings.csrf_secret or settings.csrf_secret == settings.secret_key or values.intersection({settings.csrf_secret, settings.secret_key}):
        raise SecretError('Cifrado, JWT y CSRF requieren claves independientes')
    return Keyring(settings.secret_keyring, active=settings.secret_active_key)


def redact(value):
    sensitive = {'password', 'nueva_password', 'contraseña', 'token', 'authorization', 'cookie',
                 'set-cookie', 'nonce', 'totp_secret', 'secrets', 'credenciales', 'app_key', 'secret_keyring'}
    if isinstance(value, dict):
        return {key: '[REDACTED]' if str(key).lower() in sensitive or str(key).lower().endswith('_password')
                else redact(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(child) for child in value]
    return deepcopy(value)
