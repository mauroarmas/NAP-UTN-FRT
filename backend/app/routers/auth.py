from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.usuario import Usuario, RolUsuario
from app.schemas.auth import Token, LoginRequest, Setup2FAResponse, Verify2FARequest
from app.schemas.usuario import UsuarioCreate, UsuarioResponse
from app.utils.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    decode_access_token,
    generate_totp_secret,
    get_totp_uri,
    verify_totp,
)

router = APIRouter(prefix="/auth", tags=["Autenticación"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> Usuario:
    """Dependency: obtiene el usuario actual a partir del JWT token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciales inválidas",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception

    username: str = payload.get("sub")
    if username is None:
        raise credentials_exception

    result = await db.execute(select(Usuario).where(Usuario.username == username))
    user = result.scalar_one_or_none()

    if user is None or not user.activo:
        raise credentials_exception

    return user


async def require_admin(current_user: Usuario = Depends(get_current_user)) -> Usuario:
    """Dependency: requiere rol de administrador."""
    if current_user.rol != RolUsuario.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requieren permisos de administrador",
        )
    return current_user


@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """Login con usuario y contraseña. Devuelve JWT token."""
    result = await db.execute(
        select(Usuario).where(Usuario.username == form_data.username)
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos",
        )

    if not user.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario deshabilitado",
        )

    access_token = create_access_token(
        data={"sub": user.username, "rol": user.rol.value}
    )
    return Token(access_token=access_token)


@router.get("/me", response_model=UsuarioResponse)
async def get_me(current_user: Usuario = Depends(get_current_user)):
    """Devuelve la información del usuario autenticado."""
    return current_user


@router.post("/2fa/setup", response_model=Setup2FAResponse)
async def setup_2fa(
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Genera un nuevo secreto TOTP para configurar 2FA."""
    secret = generate_totp_secret()
    uri = get_totp_uri(secret, current_user.username)

    current_user.totp_secret = secret
    await db.commit()

    return Setup2FAResponse(secret=secret, provisioning_uri=uri)


@router.post("/2fa/verify")
async def verify_2fa(
    data: Verify2FARequest,
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Verifica un código TOTP y activa 2FA para el usuario."""
    if not current_user.totp_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Primero configure 2FA con /2fa/setup",
        )

    if not verify_totp(current_user.totp_secret, data.totp_code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Código TOTP inválido",
        )

    current_user.totp_habilitado = True
    await db.commit()

    return {"message": "2FA activado correctamente"}


@router.post("/register", response_model=UsuarioResponse)
async def register_user(
    user_data: UsuarioCreate,
    current_user: Usuario = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Registra un nuevo usuario. Solo administradores."""
    # Verificar que no exista
    result = await db.execute(
        select(Usuario).where(Usuario.username == user_data.username)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El nombre de usuario ya existe",
        )

    new_user = Usuario(
        username=user_data.username,
        email=user_data.email,
        nombre=user_data.nombre,
        password_hash=get_password_hash(user_data.password),
        rol=RolUsuario(user_data.rol),
        catedra_id=user_data.catedra_id,
    )

    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    return new_user
