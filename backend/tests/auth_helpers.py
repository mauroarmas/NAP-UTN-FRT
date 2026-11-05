"""Sesión preparada solo para pruebas de dominio, sin acreditar flujo MFA."""
from app.services.auth_service import crear_sesion, establecer_cookie, csrf_token, cookie_name
from fastapi import Response


async def headers_para(db, user):
    await db.flush()
    await db.refresh(user)
    if user.debe_cambiar_password or user.totp_habilitado:
        raise AssertionError('Las etapas de habilitación se prueban con login y pruebas reales')
    session = await crear_sesion(db, user, 'operativo')
    await db.commit()
    response = Response()
    establecer_cookie(response, session, user)
    cookie = response.headers['set-cookie'].split(';', 1)[0]
    return {'Cookie': cookie, 'Origin': 'http://test', 'X-CSRF-Token': csrf_token(session), 'X-NAP-Request': '1'}
