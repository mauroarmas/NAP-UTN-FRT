from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.usuario import Usuario, RolUsuario
from app.models.catedra import Catedra
from app.routers.auth import get_current_user, require_admin
from app.schemas.usuario import UsuarioRetiroResponse, UsuarioCreate, UsuarioResponse, UsuarioUpdate
from app.services.usuario_service import (
    catedras_de,
    con_catedras,
    es_ultimo_admin_activo,
    tiene_historial,
)
from app.utils.security import get_password_hash

router = APIRouter(prefix="/usuarios", tags=["Usuarios"])


@router.get("/", response_model=list[UsuarioResponse])
async def listar_usuarios(
    incluir_bajas: bool = False,
    current_user: Usuario = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Lista las personas del sistema. Solo administradores.

    Por defecto oculta a las dadas de baja, con el mismo criterio que el
    Principio V fija para pedidos y servicios: quedan fuera de los listados
    operativos sin que eso implique que desaparecieron. `incluir_bajas` las trae.
    """
    consulta = select(Usuario).order_by(Usuario.created_at.desc())
    if not incluir_bajas:
        consulta = consulta.where(Usuario.activo.is_(True))
    result = await db.execute(consulta)
    return [await con_catedras(db, u) for u in result.scalars().all()]


@router.get("/me", response_model=UsuarioResponse)
async def get_me(
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Perfil del usuario autenticado, con sus cátedras."""
    return await con_catedras(db, current_user)


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
    return await con_catedras(db, usuario)


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

    rol = RolUsuario(data.rol)

    # Un usuario de cátedra sin cátedras no puede hacer nada: no podría crear un
    # pedido ni ver un servicio. El administrador sí puede no tener ninguna.
    if rol != RolUsuario.ADMIN and not data.catedra_ids:
        raise HTTPException(
            status_code=400,
            detail="Asigná al menos una cátedra al crear un responsable de cátedra",
        )

    # Se resuelve la disponibilidad **antes** de crear nada: si alguna cátedra
    # ya tiene titular, la operación entera se rechaza. Crear el usuario y
    # dejarlo con menos cátedras de las pedidas sería peor que no crearlo.
    catedras: list[Catedra] = []
    ocupadas: list[dict] = []
    for catedra_id in data.catedra_ids or []:
        catedra = await db.get(Catedra, catedra_id)
        if not catedra:
            raise HTTPException(
                status_code=404, detail=f"Cátedra {catedra_id} no encontrada"
            )
        if catedra.titular_id is not None:
            titular = await db.get(Usuario, catedra.titular_id)
            ocupadas.append(
                {
                    "id": catedra.id,
                    "nombre": catedra.nombre,
                    "titular": titular.nombre if titular else None,
                }
            )
        catedras.append(catedra)

    if ocupadas:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "codigo": "catedras_ya_asignadas",
                "mensaje": "Alguna de las cátedras elegidas ya tiene responsable",
                "catedras_no_disponibles": ocupadas,
            },
        )

    usuario = Usuario(
        username=data.username,
        email=data.email,
        nombre=data.nombre,
        password_hash=get_password_hash(data.password),
        rol=rol,
        activo=True,
    )
    db.add(usuario)
    await db.flush()

    for catedra in catedras:
        catedra.titular_id = usuario.id

    await db.commit()
    await db.refresh(usuario)
    return await con_catedras(db, usuario)


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

    # Las dos puertas que sacan a alguien de circulación —desactivar acá y
    # retirar en el DELETE— tienen que estar custodiadas igual, o el guard se
    # esquiva usando la otra.
    if data.activo is False and usuario.activo:
        if await es_ultimo_admin_activo(db, usuario_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "codigo": "ultimo_administrador",
                    "mensaje": (
                        "Es la única cuenta de administrador activa. Designá otro "
                        "administrador antes de dar de baja esta cuenta."
                    ),
                },
            )

    # Desactivar a alguien con cátedras a cargo las dejaría sin responsable, y
    # los servicios que cuelgan de ellas seguirían consumiendo recursos reales
    # sin nadie a quien preguntarle. Hay que resolverlo antes, no después.
    if data.activo is False and usuario.activo:
        a_cargo = await catedras_de(db, usuario_id)
        if a_cargo:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "codigo": "catedras_sin_responsable",
                    "mensaje": (
                        "Esta persona es titular de cátedras que quedarían sin "
                        "responsable. Reasignalas a otra persona antes de dar de "
                        "baja la cuenta."
                    ),
                    "catedras": [{"id": c.id, "nombre": c.nombre} for c in a_cargo],
                },
            )

    if data.nombre is not None:
        usuario.nombre = data.nombre
    if data.email is not None:
        usuario.email = data.email
    if data.rol is not None:
        usuario.rol = RolUsuario(data.rol)
    if data.activo is not None:
        usuario.activo = data.activo

    # Cambio de contraseña opcional
    if data.nueva_password:
        usuario.password_hash = get_password_hash(data.nueva_password)

    # La titularidad se reasigna acá: las cátedras que no estén en la lista
    # quedan libres, y las nuevas pasan a esta persona.
    if data.catedra_ids is not None:
        actuales = {c.id for c in await catedras_de(db, usuario_id)}
        deseadas = set(data.catedra_ids)

        for catedra_id in deseadas - actuales:
            catedra = await db.get(Catedra, catedra_id)
            if not catedra:
                raise HTTPException(
                    status_code=404, detail=f"Cátedra {catedra_id} no encontrada"
                )
            if catedra.titular_id not in (None, usuario_id):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"La cátedra '{catedra.nombre}' ya tiene otro responsable",
                )
            catedra.titular_id = usuario_id

        for catedra_id in actuales - deseadas:
            catedra = await db.get(Catedra, catedra_id)
            catedra.titular_id = None

    await db.commit()
    await db.refresh(usuario)
    return await con_catedras(db, usuario)


@router.delete("/{usuario_id}", response_model=UsuarioRetiroResponse)
async def retirar_usuario(
    usuario_id: int,
    current_user: Usuario = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Retira a una persona del sistema.

    Elige por sí solo entre baja lógica y borrado real: si la persona dejó
    historial —pedidos creados o cátedras a cargo— la cuenta se desactiva y la
    fila permanece, porque la autoría de un pedido es parte del historial
    académico. Si nunca produjo nada, se elimina de verdad.

    Quien ejecuta la acción no tiene que saber de antemano en cuál de los dos
    casos está: el sistema lo resuelve y le dice qué pasó.
    """
    if usuario_id == current_user.id:
        raise HTTPException(status_code=400, detail="No podés eliminarte a vos mismo")

    usuario = await db.get(Usuario, usuario_id)
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if await es_ultimo_admin_activo(db, usuario_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "codigo": "ultimo_administrador",
                "mensaje": (
                    "Es la única cuenta de administrador activa. Designá otro "
                    "administrador antes de dar de baja esta cuenta."
                ),
            },
        )

    a_cargo = await catedras_de(db, usuario_id)
    if a_cargo:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "codigo": "catedras_sin_responsable",
                "mensaje": (
                    "Esta persona es titular de cátedras que quedarían sin "
                    "responsable. Reasignalas a otra persona antes de dar de baja "
                    "la cuenta."
                ),
                "catedras": [{"id": c.id, "nombre": c.nombre} for c in a_cargo],
            },
        )

    username = usuario.username

    if await tiene_historial(db, usuario_id):
        usuario.activo = False
        await db.commit()
        return UsuarioRetiroResponse(
            id=usuario_id,
            username=username,
            resultado="desactivado",
            mensaje=(
                "La cuenta quedó dada de baja. Sus pedidos siguen figurando en el "
                "historial de la cátedra."
            ),
        )

    await db.delete(usuario)
    await db.commit()
    return UsuarioRetiroResponse(
        id=usuario_id,
        username=username,
        resultado="eliminado",
        mensaje="La cuenta se eliminó. No tenía pedidos ni cátedras a cargo.",
    )
