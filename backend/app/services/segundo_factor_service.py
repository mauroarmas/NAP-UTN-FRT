from datetime import timedelta
import hashlib
import hmac
import secrets
from uuid import UUID

import pyotp
from sqlalchemy import select, update

from app.models.autenticacion import DesafioAutenticacion, CodigoRecuperacion
from app.services.auth_service import usuario_bloqueado, invalidar_todas, auditar
from app.utils.clock import clock, db_utc
from app.utils.errors import error
from app.utils.secretos import configured_keyring, SecretError
from app.utils.security import verificar_password_async, generate_totp_secret, get_totp_uri


def prueba_invalida():
    return error(400, 'prueba_invalida', 'No se pudo comprobar la prueba de identidad')


async def password_correcta(user, password):
    if not await verificar_password_async(password or '', user.password_hash):
        raise prueba_invalida()


def aceptar_totp(user, code, *, secret=None):
    if not isinstance(code, str) or len(code) != 6 or not code.isascii() or not code.isdigit():
        raise prueba_invalida()
    if secret is None:
        if not user.totp_habilitado or not user.totp_secret_encrypted or user.habilitacion_inconsistente:
            raise prueba_invalida()
        try:
            secret = configured_keyring().decrypt(user.totp_secret_encrypted, context=f'totp:{user.id}')
        except SecretError:
            raise prueba_invalida() from None
    step = int(clock.now().timestamp()) // 30
    factor = pyotp.TOTP(secret)
    for candidate in [step, step - 1, step + 1]:
        if (user.totp_last_step is None or candidate > user.totp_last_step) and hmac.compare_digest(factor.at(candidate * 30), code):
            user.totp_last_step = candidate
            return
    raise prueba_invalida()


async def invalidar_codigos(db, user):
    await db.execute(update(CodigoRecuperacion).where(CodigoRecuperacion.usuario_id == user.id,
        CodigoRecuperacion.invalidado_at.is_(None)).values(invalidado_at=clock.now()))


async def emitir_codigos(db, user):
    user = await usuario_bloqueado(db, user)
    await invalidar_codigos(db, user)
    user.recovery_generation += 1
    codes = [secrets.token_hex(16) for _ in range(10)]
    for code in codes:
        db.add(CodigoRecuperacion(usuario_id=user.id, generacion=user.recovery_generation,
            codigo_hash=hashlib.sha256(code.encode()).hexdigest(), creado_at=clock.now()))
    await db.flush()
    return codes


async def consumir_codigo(db, user, code):
    user = await usuario_bloqueado(db, user)
    if not isinstance(code, str) or not 1 <= len(code) <= 200:
        raise prueba_invalida()
    entry = await db.scalar(select(CodigoRecuperacion).where(CodigoRecuperacion.usuario_id == user.id,
        CodigoRecuperacion.generacion == user.recovery_generation,
        CodigoRecuperacion.codigo_hash == hashlib.sha256(code.encode()).hexdigest(),
        CodigoRecuperacion.consumido_at.is_(None), CodigoRecuperacion.invalidado_at.is_(None)).with_for_update())
    if entry is None:
        raise prueba_invalida()
    entry.consumido_at = clock.now()
    await db.flush()


async def desafio(db, user, session, identity, kind):
    try:
        identity = UUID(str(identity))
    except (ValueError, TypeError):
        raise error(409, 'desafio_no_disponible', 'Reiniciá el paso de verificación') from None
    value = await db.scalar(select(DesafioAutenticacion).where(DesafioAutenticacion.id == identity,
        DesafioAutenticacion.usuario_id == user.id, DesafioAutenticacion.sesion_id == session.id,
        DesafioAutenticacion.tipo == kind).with_for_update().execution_options(populate_existing=True))
    if not value or value.consumido_at or value.revocado_at or db_utc(value.expira_at) <= clock.now():
        raise error(409, 'desafio_no_disponible', 'Reiniciá el paso de verificación')
    return value


async def setup(db, user, session, *, password=None, replacement=False, codigo_totp=None):
    user = await usuario_bloqueado(db, user)
    recovery = session.proposito == 'recovery'
    if not recovery:
        if bool(user.totp_habilitado) != bool(replacement):
            raise error(409, 'estado_2fa_incompatible', 'Consultá la seguridad de la cuenta antes de continuar')
        await password_correcta(user, password)
        if replacement:
            aceptar_totp(user, codigo_totp)
    # Solo una inscripción/reemplazo pendiente por cuenta. Mantiene el activo.
    await db.execute(update(DesafioAutenticacion).where(DesafioAutenticacion.usuario_id == user.id,
        DesafioAutenticacion.tipo.in_(['enrollment', 'replacement']), DesafioAutenticacion.consumido_at.is_(None),
        DesafioAutenticacion.revocado_at.is_(None)).values(revocado_at=clock.now()))
    secret = generate_totp_secret()
    value = DesafioAutenticacion(usuario_id=user.id, sesion_id=session.id,
        tipo='replacement' if replacement else 'enrollment', creado_at=clock.now(),
        expira_at=min(clock.now() + timedelta(minutes=5), db_utc(session.expira_at)))
    db.add(value)
    await db.flush()
    value.secreto_pendiente_cifrado = configured_keyring().encrypt(secret, context=f'totp-pending:{value.id}')
    auditar(db, user, '2fa_setup_iniciado')
    return {'desafio_id': str(value.id), 'secret': secret, 'provisioning_uri': get_totp_uri(secret, user.username), 'expira_at': db_utc(value.expira_at)}


async def confirmar_setup(db, user, session, identity, code, *, replacement=False):
    user = await usuario_bloqueado(db, user)
    value = await desafio(db, user, session, identity, 'replacement' if replacement else 'enrollment')
    secret = configured_keyring().decrypt(value.secreto_pendiente_cifrado, context=f'totp-pending:{value.id}')
    # El contador pertenece al factor nuevo; el viejo no se elimina antes de comprobarlo.
    previous_step = user.totp_last_step
    user.totp_last_step = None
    try:
        aceptar_totp(user, code, secret=secret)
    except Exception:
        user.totp_last_step = previous_step
        raise
    value.consumido_at = clock.now()
    value.secreto_pendiente_cifrado = None
    user.totp_secret_encrypted = configured_keyring().encrypt(secret, context=f'totp:{user.id}')
    user.totp_habilitado, user.habilitacion_inconsistente = True, False
    await db.flush()
    codes = await emitir_codigos(db, user)
    await invalidar_todas(db, user)
    auditar(db, user, '2fa_reemplazado' if replacement or session.proposito == 'recovery' else '2fa_activado')
    return codes


async def verificar_login(db, user, session, identity, code):
    user = await usuario_bloqueado(db, user)
    value = await desafio(db, user, session, identity, 'login_totp')
    aceptar_totp(user, code)
    value.consumido_at = clock.now()
    await db.flush()
    codes = await emitir_codigos(db, user) if user.recovery_generation == 0 else None
    auditar(db, user, '2fa_ingreso_verificado')
    return codes


async def cancelar_setup(db, user, session, identity):
    user = await usuario_bloqueado(db, user)
    try:
        value = await desafio(db, user, session, identity, 'enrollment')
    except Exception as exc:
        if getattr(exc, 'status_code', None) != 409:
            raise
        value = await desafio(db, user, session, identity, 'replacement')
    value.revocado_at, value.secreto_pendiente_cifrado = clock.now(), None
    auditar(db, user, '2fa_setup_cancelado')


async def recuperar(db, user, session, *, password, code, assisted=False):
    user = await usuario_bloqueado(db, user)
    await password_correcta(user, password)
    if not user.totp_habilitado:
        raise prueba_invalida()
    if assisted:
        value = await db.scalar(select(DesafioAutenticacion).where(
            DesafioAutenticacion.usuario_id == user.id, DesafioAutenticacion.tipo == 'assisted_recovery',
            DesafioAutenticacion.token_hash == hashlib.sha256(code.encode()).hexdigest(),
            DesafioAutenticacion.consumido_at.is_(None), DesafioAutenticacion.revocado_at.is_(None),
            DesafioAutenticacion.expira_at > clock.now()).with_for_update())
        if not value:
            raise prueba_invalida()
        value.consumido_at, value.sesion_id = clock.now(), session.id
        await invalidar_codigos(db, user)
    else:
        await consumir_codigo(db, user, code)
    await invalidar_todas(db, user)
    auditar(db, user, '2fa_recuperacion_asistida_consumida' if assisted else '2fa_recuperacion_codigo')


async def regenerar(db, user, *, password, codigo_totp):
    user = await usuario_bloqueado(db, user)
    await password_correcta(user, password)
    aceptar_totp(user, codigo_totp)
    await db.flush()
    codes = await emitir_codigos(db, user)
    await invalidar_todas(db, user)
    auditar(db, user, '2fa_codigos_regenerados')
    return codes


async def desactivar(db, user, *, password, codigo_totp=None, codigo_recuperacion=None):
    user = await usuario_bloqueado(db, user)
    await password_correcta(user, password)
    if not user.totp_habilitado:
        raise error(409, 'estado_2fa_incompatible', 'El segundo factor no está habilitado')
    if bool(codigo_totp) == bool(codigo_recuperacion):
        raise error(422, 'datos_invalidos', 'Presentá exactamente una prueba de segundo factor')
    if codigo_totp:
        aceptar_totp(user, codigo_totp)
    else:
        await consumir_codigo(db, user, codigo_recuperacion)
    user.totp_habilitado = False
    user.totp_secret_encrypted = user.totp_last_step = None
    user.habilitacion_inconsistente = False
    await invalidar_codigos(db, user)
    await invalidar_todas(db, user)
    auditar(db, user, '2fa_desactivado_deliberadamente')
