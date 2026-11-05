"""Sesiones con propósito, cookie protegida y revocación del lado servidor."""
from datetime import timedelta
import hashlib
import hmac
from uuid import UUID

from sqlalchemy import select, update

from app.config import get_settings
from app.models.usuario import Usuario
from app.models.autenticacion import SesionAutenticacion, DesafioAutenticacion
from app.models.evento_seguridad import EventoSeguridad
from app.utils.clock import clock, db_utc
from app.utils.errors import error
from app.utils.security import create_access_token, decode_access_token

DURATION = {'operativo': 60, 'onboarding': 15, 'mfa_pending': 5, 'recovery': 5}
ACTIONS = {
    'operativo': ['operar', 'seguridad_cuenta', 'cerrar_sesion'],
    'onboarding': ['cambiar_password_inicial', 'cerrar_sesion'],
    'mfa_pending': ['verificar_totp', 'recuperar_2fa', 'desactivar_2fa', 'cerrar_sesion'],
    'recovery': ['configurar_factor_nuevo', 'cerrar_sesion'],
}


def cookie_name():
    return 'nap_session' if get_settings().app_env == 'development' else '__Host-nap_session'


def origin_valido(request):
    settings = get_settings()
    allowed = {settings.app_frontend_url, *settings.auth_allowed_origins}
    origin = request.headers.get('origin')
    if not origin or origin == 'null' or origin not in allowed:
        raise error(403, 'origen_no_permitido', 'Origen de solicitud no permitido')


def csrf_token(session):
    secret = get_settings().csrf_secret
    if not secret or secret == get_settings().secret_key:
        raise error(503, 'configuracion_autenticacion', 'La autenticación requiere configuración de servidor')
    return hmac.new(secret.encode(), ('nap:csrf:' + str(session.id)).encode(), hashlib.sha256).hexdigest()


def exigir_csrf(request, session):
    origin_valido(request)
    supplied = request.headers.get('x-csrf-token', '')
    if not hmac.compare_digest(supplied, csrf_token(session)):
        raise error(403, 'csrf_invalido', 'Actualizá la sesión y volvé a enviar el formulario')


def exigir_proposito(session, *purposes):
    if session.proposito not in purposes:
        raise error(403, 'habilitacion_pendiente', 'Completá el acceso antes de continuar',
                    estado=session.proposito, acciones_permitidas=ACTIONS[session.proposito])


async def usuario_bloqueado(db, user):
    value = await db.scalar(select(Usuario).where(Usuario.id == user.id).with_for_update()
                            .execution_options(populate_existing=True))
    if value is None or not value.activo:
        raise error(401, 'sesion_invalida', 'Ingresá nuevamente')
    from app.services.restauracion_service import exigir_acceso_reemitido, exigir_habilitacion
    # La preparación puede haber confirmado mientras se esperaba la fila de
    # usuario; no emitir una sesión nueva después de esa revocación global.
    await exigir_habilitacion(db, componente='api')
    await exigir_acceso_reemitido(db, value)
    return value


def auditar(db, user, action, *, resultado='exitoso', actor=None, motivo=None, referencia=None):
    db.add(EventoSeguridad(usuario_objetivo_id=user.id if user else None,
        actor_usuario_id=actor.id if actor else (user.id if user else None), accion=action,
        resultado=resultado, motivo=motivo, referencia=referencia))


async def revocar(db, session):
    now = clock.now()
    session.revoked_at = now
    await db.execute(update(DesafioAutenticacion).where(DesafioAutenticacion.sesion_id == session.id,
        DesafioAutenticacion.consumido_at.is_(None), DesafioAutenticacion.revocado_at.is_(None)).values(revocado_at=now))


async def invalidar_todas(db, user):
    user.auth_version += 1
    now = clock.now()
    await db.execute(update(SesionAutenticacion).where(SesionAutenticacion.usuario_id == user.id,
        SesionAutenticacion.revoked_at.is_(None)).values(revoked_at=now))
    await db.execute(update(DesafioAutenticacion).where(DesafioAutenticacion.usuario_id == user.id,
        DesafioAutenticacion.consumido_at.is_(None), DesafioAutenticacion.revocado_at.is_(None)).values(revocado_at=now))


async def crear_sesion(db, user, purpose, *, anterior=None, mfa_at=None):
    if anterior:
        await revocar(db, anterior)
    now = clock.now()
    session = SesionAutenticacion(usuario_id=user.id, proposito=purpose, auth_version=user.auth_version,
        creada_at=now, expira_at=now + timedelta(minutes=DURATION[purpose]), mfa_verified_at=mfa_at)
    db.add(session)
    await db.flush()
    if purpose == 'mfa_pending':
        db.add(DesafioAutenticacion(usuario_id=user.id, sesion_id=session.id, tipo='login_totp',
            creado_at=now, expira_at=session.expira_at))
        await db.flush()
    return session


def establecer_cookie(response, session, user):
    now = clock.now()
    token = create_access_token({'sid': str(session.id), 'sub': str(user.id), 'iat': int(now.timestamp()),
        'auth_version': user.auth_version, 'exp': int(db_utc(session.expira_at).timestamp())},
        expires_delta=db_utc(session.expira_at) - now)
    response.set_cookie(cookie_name(), token, httponly=True, secure=get_settings().app_env != 'development',
        samesite='lax', path='/', max_age=max(0, int((db_utc(session.expira_at) - now).total_seconds())))
    response.headers['Cache-Control'] = 'no-store'


def borrar_cookie(response):
    response.delete_cookie(cookie_name(), httponly=True, secure=get_settings().app_env != 'development', samesite='lax', path='/')
    response.headers['Cache-Control'] = 'no-store'


async def autenticar(db, request, *, mutation_csrf=True):
    from app.services.restauracion_service import exigir_habilitacion, exigir_acceso_reemitido
    await exigir_habilitacion(db, componente='api')
    invalid = error(401, 'sesion_invalida', 'Ingresá nuevamente')
    token = request.cookies.get(cookie_name())
    if not token:
        raise invalid
    claims = decode_access_token(token)
    try:
        if not claims or not {'sid', 'sub', 'iat', 'exp', 'auth_version'} <= set(claims):
            raise ValueError()
        identity, user_id = UUID(claims['sid']), int(claims['sub'])
        if type(claims['auth_version']) is not int or type(claims['iat']) is not int:
            raise ValueError()
    except (ValueError, TypeError, KeyError):
        raise invalid
    session = await db.get(SesionAutenticacion, identity, populate_existing=True)
    user = await db.get(Usuario, user_id, populate_existing=True)
    if not session or not user or not user.activo or session.usuario_id != user_id or session.revoked_at or (
        db_utc(session.expira_at) <= clock.now() or session.auth_version != user.auth_version or claims['auth_version'] != user.auth_version):
        raise invalid
    # Fechas de servidor y token deben concordar; no se prolonga por actividad.
    if claims['exp'] != int(db_utc(session.expira_at).timestamp()) or claims['iat'] > int(clock.now().timestamp()) + 30:
        raise invalid
    request.state.auth_session = session
    await exigir_acceso_reemitido(db, user)
    if mutation_csrf and request.method not in {'GET', 'HEAD', 'OPTIONS'}:
        exigir_csrf(request, session)
    return user, session


async def presentar(db, user, session, *, rotated=False):
    result = {'estado': session.proposito, 'expira_at': db_utc(session.expira_at),
              'sesion_rotada': rotated, 'acciones_permitidas': ACTIONS[session.proposito]}
    challenge = await db.scalar(select(DesafioAutenticacion).where(
        DesafioAutenticacion.sesion_id == session.id, DesafioAutenticacion.tipo == 'login_totp',
        DesafioAutenticacion.consumido_at.is_(None), DesafioAutenticacion.revocado_at.is_(None),
        DesafioAutenticacion.expira_at > clock.now()))
    if challenge:
        result['desafio'] = {'id': str(challenge.id), 'expira_at': db_utc(challenge.expira_at)}
    return result
