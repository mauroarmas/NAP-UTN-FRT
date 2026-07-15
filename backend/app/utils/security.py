from datetime import datetime, timedelta

from jose import jwt, JWTError
from passlib.context import CryptContext
import pyotp

from app.config import get_settings

settings = get_settings()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica una contraseña contra su hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Genera el hash bcrypt de una contraseña."""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Crea un JWT token con los datos proporcionados."""
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> dict | None:
    """Decodifica y valida un JWT token."""
    try:
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[settings.algorithm]
        )
        return payload
    except JWTError:
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
