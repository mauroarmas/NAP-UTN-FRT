import logging

from cryptography.fernet import Fernet
import pytest


def test_rotation_preserves_existing_secrets_and_binds_them_to_their_context():
    from app.utils.secretos import Keyring, SecretError
    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    initial = Keyring({'old': old}, active='old')
    token = initial.encrypt({'password': 'private-value'}, context='servicio:9')
    rotated = Keyring({'old': old, 'new': new}, active='new')
    assert rotated.decrypt(token, context='servicio:9') == {'password': 'private-value'}
    replacement = rotated.rotate(token, context='servicio:9')
    assert replacement.startswith('v1:new:')
    assert rotated.decrypt(replacement, context='servicio:9') == {'password': 'private-value'}
    with pytest.raises(SecretError):
        rotated.decrypt(token, context='servicio:10')


def test_invalid_key_or_token_never_appears_in_errors_or_logs(caplog):
    from app.utils.secretos import Keyring, SecretError, redact
    with pytest.raises(SecretError) as exc:
        Keyring({'one': 'invalid-private-key'}, active='one')
    assert 'invalid-private-key' not in str(exc.value)
    keyring = Keyring({'one': Fernet.generate_key().decode()}, active='one')
    with pytest.raises(SecretError) as exc:
        keyring.decrypt('invalid-private-token', context='totp:1')
    assert 'invalid-private-token' not in str(exc.value)
    with caplog.at_level(logging.INFO):
        logging.getLogger('test').info('%s', redact({'password': 'sensitive123', 'nested': {'app_key': 'key123'}}))
    assert 'sensitive123' not in caplog.text and 'key123' not in caplog.text


def test_keyring_rejects_reuse_of_authentication_keys():
    from app.config import Settings
    from app.utils.secretos import configured_keyring, SecretError
    key = Fernet.generate_key().decode()
    settings = Settings(secret_key=key, csrf_secret='different', secret_keyring={'one': key}, secret_active_key='one')
    with pytest.raises(SecretError):
        configured_keyring(settings)
