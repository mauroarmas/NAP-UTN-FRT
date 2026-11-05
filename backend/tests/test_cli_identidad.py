from datetime import datetime, timezone
import hashlib

import pyotp
import pytest
from sqlalchemy import select

from app.models.autenticacion import DesafioAutenticacion
from app.models.usuario import Usuario, RolUsuario
from app.utils.secretos import configured_keyring
from scripts.bootstrap_admin import create_initial
from scripts.recuperar_2fa import emitir
from tests.test_auth_contrato_009 import auth_configuration, ingresar, csrf

pytestmark = pytest.mark.usefixtures('auth_configuration')


async def test_bootstrap_once_without_defaults_or_replacing_inactive_admin(db):
    user = await create_initial(db, username='institutional', nombre='Titular', email='titular@example.org', password='Inicial123!', actor='operador')
    await db.commit()
    assert user.debe_cambiar_password and not user.totp_habilitado
    user.activo = False
    await db.commit()
    with pytest.raises(ValueError):
        await create_initial(db, username='auxiliary', nombre='Auxiliar', email='aux@example.org', password='Auxiliar123!', actor='operador')
    assert len((await db.scalars(select(Usuario))).all()) == 1


async def test_sole_admin_assisted_recovery_replaces_factor_without_auxiliary_account(client, db, admin, monkeypatch):
    from app.utils.clock import clock
    instant = datetime(2026, 10, 20, 18, tzinfo=timezone.utc)
    monkeypatch.setattr(clock, 'now', lambda: instant)
    original = pyotp.random_base32()
    admin.totp_habilitado = True
    admin.totp_secret_encrypted = configured_keyring().encrypt(original, context=f'totp:{admin.id}')
    await db.commit()
    token = await emitir(db, usuario=admin.username, actor='operador', motivo='Identidad comprobada', referencia='ACTA-TEST-001')
    await db.commit()
    entry = await db.scalar(select(DesafioAutenticacion).where(DesafioAutenticacion.token_hash == hashlib.sha256(token.encode()).hexdigest()))
    assert entry and entry.sesion_id is None and not hasattr(entry, 'token')
    assert (await ingresar(client, admin)).json()['estado'] == 'mfa_pending'
    response = await client.post('/auth/2fa/assisted-recovery', headers=await csrf(client), json={'password': 'secreto123', 'autorizacion_recuperacion': token})
    assert response.json()['estado'] == 'recovery'
    assert (await client.get('/usuarios/')).status_code == 403
    setup = (await client.post('/auth/2fa/setup', headers=await csrf(client), json={})).json()
    confirmed = await client.post('/auth/2fa/verify', headers=await csrf(client), json={'desafio_id': setup['desafio_id'], 'codigo_totp': pyotp.TOTP(setup['secret']).at(instant)})
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()['estado'] == 'operativo'
    assert len((await db.scalars(select(Usuario).where(Usuario.rol == RolUsuario.ADMIN))).all()) == 1
    await db.refresh(entry)
    assert entry.consumido_at and entry.sesion_id


async def test_emitting_again_revokes_prior_authorization_and_does_not_change_password_or_factor(db, admin):
    admin.totp_habilitado = True
    await db.commit()
    password_hash = admin.password_hash
    first = await emitir(db, usuario=admin.username, actor='operador', motivo='Identidad comprobada', referencia='ACTA-1')
    await db.commit()
    second = await emitir(db, usuario=admin.username, actor='operador', motivo='Reemisión autorizada', referencia='ACTA-2')
    await db.commit()
    assert first != second
    rows = (await db.scalars(select(DesafioAutenticacion))).all()
    assert sum(row.revocado_at is None for row in rows) == 1
    assert admin.password_hash == password_hash and admin.totp_habilitado


def test_cli_refuses_redirected_output(monkeypatch, capsys):
    from scripts import recuperar_2fa
    monkeypatch.setattr('sys.argv', ['recuperar_2fa', '--usuario', 'admin', '--actor', 'operador', '--motivo', 'identidad', '--referencia', 'ACTA-1'])
    monkeypatch.setattr('sys.stdout.isatty', lambda: False)
    assert recuperar_2fa.main() == 2
    assert 'sin redirecciones' in capsys.readouterr().out
