import asyncio
from datetime import datetime, timedelta, timezone

import jwt
from jwt import InvalidTokenError
from passlib.context import CryptContext
import pyotp

from app.config import get_settings
from app.utils.clock import clock

settings = get_settings()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_bcrypt_slots = asyncio.Semaphore(4)


def validar_password(password: str, *, nueva=False):
    if not isinstance(password, str) or len(password.encode('utf-8')) > 72 or (nueva and len(password) < 8):
        from app.utils.errors import error
        raise error(422, 'datos_invalidos', 'La contraseña nueva requiere al menos 8 caracteres y toda contraseña admite hasta 72 bytes UTF-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica una contraseña contra su hash."""
    if not isinstance(plain_password, str) or len(plain_password.encode('utf-8')) > 72:
        return False
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except (ValueError, TypeError):
        return False


def get_password_hash(password: str) -> str:
    """Genera el hash bcrypt de una contraseña."""
    validar_password(password, nueva=True)
    return pwd_context.hash(password)


async def verificar_password_async(password, encoded):
    validar_password(password)
    async with _bcrypt_slots:
        return await asyncio.to_thread(verify_password, password, encoded)


async def hash_password_async(password):
    validar_password(password, nueva=True)
    async with _bcrypt_slots:
        return await asyncio.to_thread(get_password_hash, password)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Crea un JWT token con los datos proporcionados."""
    to_encode = data.copy()
    expire = clock.now() + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode.setdefault('exp', expire)
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> dict | None:
    """Decodifica y valida un JWT token."""
    try:
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[settings.algorithm],
            options={'verify_exp':False,'verify_iat':False,'verify_nbf':False,'require':['exp']}
        )
        # Un único reloj para JWT, sesiones y desafíos, también en pruebas de vencimiento.
        instant=clock.now().timestamp()
        if type(payload.get('exp')) is not int or payload['exp'] <= instant:
            return None
        if any(name in payload and (type(payload[name]) is not int or payload[name]>instant) for name in ['iat','nbf']):
            return None
        return payload
    except InvalidTokenError:
        return None


def generate_totp_secret() -> str:
    """Genera un nuevo secreto TOTP para 2FA."""
    return pyotp.random_base32()


def get_totp_uri(secret: str, username: str) -> str:
    """Genera la URI de provisioning para apps autenticadoras (Google Authenticator, etc.)."""
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=username, issuer_name=settings.app_name)


def verify_totp(secret: str, code: str) -> bool:
    """Verifica un código TOTP."""
    totp = pyotp.TOTP(secret)
    return totp.verify(code)
