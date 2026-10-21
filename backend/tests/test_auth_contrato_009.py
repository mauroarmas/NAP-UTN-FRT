from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet
import pyotp
import pytest

from app.config import get_settings
from tests import factories

ORIGIN = {'Origin': 'http://test', 'X-NAP-Request': '1'}


@pytest.fixture
def auth_configuration(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, 'app_env', 'development')
    monkeypatch.setattr(settings, 'app_frontend_url', 'http://test')
    monkeypatch.setattr(settings, 'csrf_secret', 'test-csrf-independent-key-009-only')
    monkeypatch.setattr(settings, 'secret_keyring', {'test': Fernet.generate_key().decode()})
    monkeypatch.setattr(settings, 'secret_active_key', 'test')
    return settings


async def ingresar(client, user, password='secreto123'):
    return await client.post('/auth/login', data={'username': user.username, 'password': password}, headers=ORIGIN)


async def csrf(client):
    response = await client.get('/auth/csrf')
    assert response.status_code == 200, response.text
    return ORIGIN | {'X-CSRF-Token': response.json()['csrf_token']}


async def test_cookie_login_optional_mfa_and_real_logout(client, db, auth_configuration):
    user = await factories.crear_usuario(db, 'optional_mfa')
    response = await ingresar(client, user)
    assert response.status_code == 200, response.text
    assert response.json()['estado'] == 'operativo'
    assert 'access_token' not in response.json()
    assert 'HttpOnly' in response.headers['set-cookie']
    assert 'SameSite=lax' in response.headers['set-cookie']
    assert response.headers['cache-control'] == 'no-store'
    me = await client.get('/auth/me')
    assert me.json()['usuario']['totp_habilitado'] is False
    old_cookie = client.cookies.get('nap_session')
    denied = await client.post('/auth/logout', headers=ORIGIN)
    assert denied.status_code == 403
    headers = await csrf(client)
    assert (await client.post('/auth/logout', headers=headers)).status_code == 204
    client.cookies.set('nap_session', old_cookie)
    assert (await client.get('/auth/me')).status_code == 401


async def test_login_requires_deliberate_allowed_origin(client, db, auth_configuration):
    client.headers.clear()
    user = await factories.crear_usuario(db, 'origin')
    for headers in [{}, {'Origin': 'null', 'X-NAP-Request': '1'}, {'Origin': 'https://foreign', 'X-NAP-Request': '1'}, {'Origin': 'http://test'}]:
        result = await client.post('/auth/login', data={'username': user.username, 'password': 'secreto123'}, headers=headers)
        assert result.status_code == 403
        assert 'set-cookie' not in result.headers


async def test_onboarding_blocks_domain_and_rotates_sid_after_exact_password(client, db, auth_configuration):
    user = await factories.crear_usuario(db, 'onboarding')
    user.debe_cambiar_password = True
    await db.commit()
    assert (await ingresar(client, user)).json()['estado'] == 'onboarding'
    initial = client.cookies.get('nap_session')
    assert (await client.get('/pedidos/')).json()['detail']['codigo'] == 'habilitacion_pendiente'
    headers = await csrf(client)
    response = await client.post('/auth/cambiar-password-inicial', json={'nueva_password': ' EspaciosConservados123 '}, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()['estado'] == 'operativo'
    assert client.cookies.get('nap_session') != initial
    assert (await client.post('/auth/logout', headers=headers)).status_code == 403
    client.cookies.clear()
    assert (await ingresar(client, user, 'EspaciosConservados123')).status_code == 401
    assert (await ingresar(client, user, ' EspaciosConservados123 ')).status_code == 200


async def test_bearer_legacy_without_server_session_is_rejected(client, db, auth_configuration):
    from app.utils.security import create_access_token
    user = await factories.crear_usuario(db, 'legacy')
    token = create_access_token({'sub': user.username, 'rol': 'admin'})
    assert (await client.get('/auth/me', headers={'Authorization': 'Bearer ' + token})).status_code == 401


async def test_setup_is_optional_cancelled_and_expires_without_enabling(client, db, auth_configuration, monkeypatch):
    from app.utils.clock import clock
    instant = datetime(2026, 10, 20, 15, tzinfo=timezone.utc)
    monkeypatch.setattr(clock, 'now', lambda: instant)
    user = await factories.crear_usuario(db, 'setup')
    await ingresar(client, user)
    response = await client.post('/auth/2fa/setup', headers=await csrf(client), json={'password': 'secreto123'})
    assert response.status_code == 200, response.text
    challenge = response.json()['desafio_id']
    await db.refresh(user)
    assert user.totp_habilitado is False
    cancelled = await client.request('DELETE', '/auth/2fa/setup', headers=await csrf(client), json={'desafio_id': challenge})
    assert cancelled.status_code == 204
    assert (await client.get('/auth/me')).json()['estado'] == 'operativo'
    second = await client.post('/auth/2fa/setup', headers=await csrf(client), json={'password': 'secreto123'})
    instant += timedelta(minutes=6)
    expired = await client.post('/auth/2fa/verify', headers=await csrf(client), json={'desafio_id': second.json()['desafio_id'], 'codigo_totp': pyotp.TOTP(second.json()['secret']).at(instant)})
    assert expired.status_code == 409
    await db.refresh(user)
    assert user.totp_habilitado is False


async def test_recovery_is_restricted_until_new_factor_and_codes_are_single_use(client, db, auth_configuration, monkeypatch):
    from app.utils.clock import clock
    instant = datetime(2026, 10, 20, 15, tzinfo=timezone.utc)
    monkeypatch.setattr(clock, 'now', lambda: instant)
    user = await factories.crear_usuario(db, 'recovery')
    await ingresar(client, user)
    setup = (await client.post('/auth/2fa/setup', headers=await csrf(client), json={'password': 'secreto123'})).json()
    activated = await client.post('/auth/2fa/verify', headers=await csrf(client), json={'desafio_id': setup['desafio_id'], 'codigo_totp': pyotp.TOTP(setup['secret']).at(instant)})
    assert activated.status_code == 200, activated.text
    codes = activated.json()['codigos_recuperacion']
    assert len(codes) == len(set(codes)) == 10
    await client.post('/auth/logout', headers=await csrf(client))
    login = await ingresar(client, user)
    assert login.json()['estado'] == 'mfa_pending'
    challenge = login.json()['desafio']['id']
    replay = await client.post('/auth/2fa/challenge/verify', headers=await csrf(client), json={'desafio_id': challenge, 'codigo_totp': pyotp.TOTP(setup['secret']).at(instant)})
    assert replay.status_code == 400
    recovered = await client.post('/auth/2fa/recovery', headers=await csrf(client), json={'password': 'secreto123', 'codigo_recuperacion': codes[0]})
    assert recovered.json()['estado'] == 'recovery'
    assert (await client.get('/servicios/')).status_code == 403
    assert (await client.post('/auth/2fa/disable', headers=await csrf(client), json={'password': 'secreto123', 'codigo_recuperacion': codes[1]})).status_code == 403
    replacement = (await client.post('/auth/2fa/setup', headers=await csrf(client), json={})).json()
    await db.refresh(user)
    assert user.totp_habilitado is True
    assert replacement['secret'] != setup['secret']
    confirmed = await client.post('/auth/2fa/verify', headers=await csrf(client), json={'desafio_id': replacement['desafio_id'], 'codigo_totp': pyotp.TOTP(replacement['secret']).at(instant)})
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()['estado'] == 'operativo'
    assert not set(codes) & set(confirmed.json()['codigos_recuperacion'])
    await client.post('/auth/logout', headers=await csrf(client))
    await ingresar(client, user)
    consumed = await client.post('/auth/2fa/recovery', headers=await csrf(client), json={'password': 'secreto123', 'codigo_recuperacion': codes[0]})
    assert consumed.status_code == 400
    assert (await client.get('/auth/me')).json()['estado'] == 'mfa_pending'


async def test_disabling_requires_new_proof_closes_all_sessions_and_preserves_password(client, db, auth_configuration, monkeypatch):
    from app.utils.clock import clock
    instant = datetime(2026, 10, 20, 20, tzinfo=timezone.utc)
    monkeypatch.setattr(clock, 'now', lambda: instant)
    user = await factories.crear_usuario(db, 'disable')
    await ingresar(client, user)
    setup = (await client.post('/auth/2fa/setup', headers=await csrf(client), json={'password': 'secreto123'})).json()
    enabled = await client.post('/auth/2fa/verify', headers=await csrf(client), json={'desafio_id': setup['desafio_id'], 'codigo_totp': pyotp.TOTP(setup['secret']).at(instant)})
    assert enabled.status_code == 200
    cookie = client.cookies.get('nap_session')
    instant += timedelta(seconds=30)
    disabled = await client.post('/auth/2fa/disable', headers=await csrf(client), json={'password': 'secreto123', 'codigo_totp': pyotp.TOTP(setup['secret']).at(instant)})
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()['estado'] == 'sesion_finalizada'
    assert not client.cookies.get('nap_session')
    client.cookies.set('nap_session', cookie)
    assert (await client.get('/auth/me')).status_code == 401
    client.cookies.clear()
    assert (await ingresar(client, user)).json()['estado'] == 'operativo'
    await db.refresh(user)
    assert not user.totp_habilitado and user.totp_secret_encrypted is None


async def test_passwords_over_bcrypt_limit_are_rejected_without_truncation(client, db, auth_configuration):
    user = await factories.crear_usuario(db, 'bytes')
    result = await ingresar(client, user, 'é' * 37)
    assert result.status_code == 422


async def test_operational_cookie_is_host_scoped_secure(client, db, auth_configuration, monkeypatch):
    monkeypatch.setattr(auth_configuration, 'app_env', 'production')
    user = await factories.crear_usuario(db, 'secure')
    response = await ingresar(client, user)
    cookie = response.headers['set-cookie']
    assert cookie.startswith('__Host-nap_session=')
    assert 'Secure' in cookie and 'HttpOnly' in cookie and 'Path=/' in cookie
    assert 'Domain=' not in cookie


def test_forwarded_origin_is_accepted_only_from_configured_proxy(auth_configuration, monkeypatch):
    from starlette.requests import Request
    from app.services.auth_intentos_service import origen_remoto
    request = Request({'type': 'http', 'client': ('127.0.0.1', 1234), 'headers': [(b'x-forwarded-for', b'192.0.2.14')]})
    assert origen_remoto(request) == '127.0.0.1'
    monkeypatch.setattr(auth_configuration, 'trusted_proxy_networks', ['127.0.0.1/32'])
    assert origen_remoto(request) == '192.0.2.14'
