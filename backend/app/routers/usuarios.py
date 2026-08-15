from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.usuario import Usuario, RolUsuario
from app.models.catedra import Catedra
from app.routers.auth import get_current_user, require_admin
from app.schemas.usuario import UsuarioCreate, UsuarioResponse, UsuarioUpdate
from app.utils.security import get_password_hash

router = APIRouter(prefix="/usuarios", tags=["Usuarios"])


@router.get("/", response_model=list[UsuarioResponse])
async def listar_usuarios(
    current_user: Usuario = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Lista todos los usuarios del sistema. Solo administradores."""
    result = await db.execute(select(Usuario).order_by(Usuario.created_at.desc()))
    return result.scalars().all()


@router.get("/me", response_model=UsuarioResponse)
async def get_me(current_user: Usuario = Depends(get_current_user)):
    """Perfil del usuario autenticado."""
    return current_user


@router.get("/{usuario_id}", response_model=UsuarioResponse)
async def obtener_usuario(
    usuario_id: int,
    current_user: Usuario = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Obtiene un usuario por ID. Solo administradores."""
    usuario = await db.get(Usuario, usuario_id)
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return usuario


@router.post("/", response_model=UsuarioResponse, status_code=201)
async def crear_usuario(
    data: UsuarioCreate,
    current_user: Usuario = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Crea un nuevo usuario. Solo administradores."""
    # Verificar username único
    result = await db.execute(
        select(Usuario).where(Usuario.username == data.username)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="El nombre de usuario ya existe")

    # Verificar email único si viene
    if data.email:
        result = await db.execute(
            select(Usuario).where(Usuario.email == data.email)
        )
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="El email ya está registrado")

    # Verificar cátedra si se asigna
    if data.catedra_id:
        catedra = await db.get(Catedra, data.catedra_id)
        if not catedra:
            raise HTTPException(status_code=404, detail="Cátedra no encontrada")

    usuario = Usuario(
        username=data.username,
        email=data.email,
        nombre=data.nombre,
        password_hash=get_password_hash(data.password),
        rol=RolUsuario(data.rol),
        catedra_id=data.catedra_id,
        activo=True,
    )
    db.add(usuario)
    await db.commit()
    await db.refresh(usuario)
    return usuario


@router.patch("/{usuario_id}", response_model=UsuarioResponse)
async def actualizar_usuario(
    usuario_id: int,
    data: UsuarioUpdate,
    current_user: Usuario = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Actualiza nombre, email, cátedra, rol o estado de un usuario."""
    usuario = await db.get(Usuario, usuario_id)
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # No permitir que el admin se desactive a sí mismo
    if usuario_id == current_user.id and data.activo is False:
        raise HTTPException(
            status_code=400, detail="No podés desactivar tu propia cuenta"
        )

    if data.nombre is not None:
        usuario.nombre = data.nombre
    if data.email is not None:
        usuario.email = data.email
    if data.rol is not None:
        usuario.rol = RolUsuario(data.rol)
    if data.catedra_id is not None:
        catedra = await db.get(Catedra, data.catedra_id)
        if not catedra:
            raise HTTPException(status_code=404, detail="Cátedra no encontrada")
        usuario.catedra_id = data.catedra_id
    if data.activo is not None:
        usuario.activo = data.activo

    # Cambio de contraseña opcional
    if data.nueva_password:
        usuario.password_hash = get_password_hash(data.nueva_password)

    await db.commit()
    await db.refresh(usuario)
    return usuario


@router.delete("/{usuario_id}", status_code=204)
async def eliminar_usuario(
    usuario_id: int,
    current_user: Usuario = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Elimina un usuario. No se puede eliminar a uno mismo."""
    if usuario_id == current_user.id:
        raise HTTPException(status_code=400, detail="No podés eliminarte a vos mismo")

    usuario = await db.get(Usuario, usuario_id)
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    await db.delete(usuario)
    await db.commit()
