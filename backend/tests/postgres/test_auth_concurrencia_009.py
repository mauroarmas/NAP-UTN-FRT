import asyncio
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
import pyotp
import pytest

from tests.test_auth_contrato_009 import auth_configuration

pytestmark = pytest.mark.usefixtures("auth_configuration")

from app.models.usuario import Usuario


async def test_same_recovery_code_is_consumed_once_across_sessions(db, pg_sessions, admin):
    from app.services.segundo_factor_service import emitir_codigos, consumir_codigo
    codes = await emitir_codigos(db, admin)
    await db.commit()
    identity = admin.id
    barrier = asyncio.Barrier(2)

    async def consume():
        async with pg_sessions() as session, session.begin():
            user = await session.get(Usuario, identity)
            await barrier.wait()
            try:
                await consumir_codigo(session, user, codes[0])
                return True
            except HTTPException:
                return False

    assert sorted(await asyncio.gather(consume(), consume())) == [False, True]


async def test_totp_replay_cannot_regenerate_and_disable_concurrently(db, pg_sessions, admin, monkeypatch):
    from app.services.segundo_factor_service import regenerar, desactivar
    from app.utils.secretos import configured_keyring
    from app.utils.clock import clock
    instant = datetime(2026, 10, 20, 15, tzinfo=timezone.utc)
    monkeypatch.setattr(clock, 'now', lambda: instant)
    secret = pyotp.random_base32()
    admin.totp_habilitado = True
    admin.totp_secret_encrypted = configured_keyring().encrypt(secret, context=f'totp:{admin.id}')
    await db.commit()
    identity, code = admin.id, pyotp.TOTP(secret).at(instant)
    barrier = asyncio.Barrier(2)

    async def change(disable):
        async with pg_sessions() as session, session.begin():
            user = await session.get(Usuario, identity)
            await barrier.wait()
            try:
                if disable:
                    await desactivar(session, user, password='secreto123', codigo_totp=code)
                else:
                    await regenerar(session, user, password='secreto123', codigo_totp=code)
                return True
            except HTTPException:
                return False

    assert sorted(await asyncio.gather(change(False), change(True))) == [False, True]


async def test_failure_limit_is_sliding_across_quarter_hour(db, monkeypatch):
    from app.services.auth_intentos_service import comprobar_limite, registrar_fallo
    from app.utils.clock import clock
    instant = datetime(2026, 10, 20, 15, 14, 50, tzinfo=timezone.utc)
    monkeypatch.setattr(clock, 'now', lambda: instant)
    for _ in range(4):
        await comprobar_limite(db, 'account:fixture', '127.0.0.1')
        await registrar_fallo(db, 'account:fixture', '127.0.0.1')
        await db.commit()
    instant += timedelta(seconds=20)
    await comprobar_limite(db, 'account:fixture', '127.0.0.1')
    await registrar_fallo(db, 'account:fixture', '127.0.0.1')
    await db.commit()
    try:
        await comprobar_limite(db, 'account:fixture', '127.0.0.1')
    except HTTPException as exc:
        assert exc.status_code == 429
        assert exc.headers['Retry-After'] == '900'
    else:
        raise AssertionError('El cambio de cuarto de hora no debe reiniciar la ventana')


async def test_concurrent_failures_share_one_account_window(pg_sessions):
    from app.services.auth_intentos_service import comprobar_limite, registrar_fallo
    from app.models.autenticacion import IntentoAutenticacion
    from sqlalchemy import select
    barrier = asyncio.Barrier(10)
    async def fail():
        async with pg_sessions() as session, session.begin():
            await barrier.wait()
            try:
                await comprobar_limite(session, 'same-account', '127.0.0.1')
                await registrar_fallo(session, 'same-account', '127.0.0.1')
                return 'recorded'
            except HTTPException as exc:
                assert exc.status_code == 429
                return 'blocked'
    results = await asyncio.gather(*(fail() for _ in range(10)))
    assert results.count('recorded') == 5
    assert results.count('blocked') == 5
    async with pg_sessions() as session:
        entries = (await session.scalars(select(IntentoAutenticacion))).all()
        assert len(entries) == 2
        assert all(len(entry.fallos_recientes) == 5 for entry in entries)
