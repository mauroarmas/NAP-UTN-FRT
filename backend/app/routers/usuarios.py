from app.services.usuario_service import exigir_gestion
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Header
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models.usuario import Usuario, RolUsuario
from app.models.catedra import Catedra
from app.routers.auth import get_current_user, require_admin
from app.schemas.usuario import UsuarioRetiroResponse, UsuarioCreate, UsuarioResponse, UsuarioUpdate
from app.services.notificacion_service import encolar_bienvenida
from app.services.usuario_service import (
    catedras_de,
    con_catedras,
    es_ultimo_admin_activo,
    generar_password_provisoria,
)
from app.utils.security import get_password_hash
from app.services.consola_access_service import solicitar_cambio
from app.utils.responses import respuesta_decision
from app.utils.errors import error

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
    background_tasks: BackgroundTasks,
    current_user: Usuario = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Crea un nuevo usuario con contraseña provisoria automática. Solo administradores."""
    current_user = await exigir_gestion(db, current_user)
    # Verificar email obligatorio
    if not data.email or not data.email.strip():
        raise HTTPException(status_code=400, detail="El email es obligatorio")

    # Verificar username único
    result = await db.execute(
        select(Usuario).where(func.lower(Usuario.username) == data.username.casefold())
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="El nombre de usuario ya existe")

    # Verificar email único
    result = await db.execute(
        select(Usuario).where(func.lower(Usuario.email) == data.email.casefold())
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
    # ya tiene titular, la operación entera se rechaza.
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

    password_provisoria = data.password or generar_password_provisoria()

    usuario = Usuario(
        username=data.username,
        email=data.email,
        nombre=data.nombre,
        password_hash=get_password_hash(password_provisoria),
        rol=rol,
        activo=True,
        debe_cambiar_password=True,
        recibir_notificaciones_email=True,
        inventario_consola='sin_identidad',
        inventario_consola_ref='ALTA-PORTAL-SIN-CONCESION-NATIVA',
        inventario_consola_actor=current_user.username,
    )
    db.add(usuario)
    await db.flush()

    for catedra in catedras:
        catedra.titular_id = usuario.id

    await encolar_bienvenida(db, usuario, password_provisoria)
    await db.commit()
    await db.refresh(usuario)

    return await con_catedras(db, usuario)


@router.patch("/{usuario_id}", response_model=UsuarioResponse)
async def actualizar_usuario(
    usuario_id: int,
    data: UsuarioUpdate,
    current_user: Usuario = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    clave: str | None = Header(default=None, alias='Idempotency-Key'),
):
    """Actualiza nombre, email, cátedra, rol o estado de un usuario."""
    current_user = await exigir_gestion(db, current_user)
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

    changes = {key: value for key, value in data.model_dump(exclude_unset=True).items()
               if key not in {'revision_esperada', 'nueva_password'} and value is not None}
    if data.email is not None and await db.scalar(select(Usuario.id).where(
        func.lower(Usuario.email) == data.email, Usuario.id != usuario.id).limit(1)):
        raise error(409, 'email_en_uso', 'Otra cuenta ya utiliza ese correo')
    previous_categories = {row.id for row in await catedras_de(db, usuario.id)}
    critical = (data.rol is not None and data.rol != usuario.rol.value and usuario.rol == RolUsuario.ADMIN) or (
        data.activo is False and usuario.activo) or (
        data.catedra_ids is not None and not previous_categories <= set(data.catedra_ids))
    if critical:
        if data.nueva_password:
            raise error(422, 'cambios_separados', 'Guardá el cambio de contraseña por separado del cambio de permisos')
        if usuario.inventario_consola == 'asignada' and (not clave or data.revision_esperada is None):
            raise error(422, 'revision_o_clave_ausente', 'El cambio nativo requiere revisión y clave idempotente')
        action = 'desactivar' if data.activo is False else ('cambiar_rol' if data.rol != usuario.rol.value and data.rol is not None else 'reasignar')
        result = await solicitar_cambio(db, usuario_objetivo_id=usuario.id, catedra_id=None,
            accion=action, cambios=changes, revision_esperada=data.revision_esperada or usuario.revision_admin,
            actor=current_user, clave=clave or 'local:' + str(uuid4()))
        await db.commit()
        return respuesta_decision(result)

    if data.revision_esperada is not None and data.revision_esperada != usuario.revision_admin:
        raise error(409, 'revision_desactualizada', 'Recargá los datos antes de guardar')
    from app.models.cambio_acceso_consola import CambioAccesoConsola
    if await db.scalar(select(CambioAccesoConsola.id).where(CambioAccesoConsola.usuario_id == usuario.id,
        CambioAccesoConsola.estado.in_(['pendiente', 'revocacion_fallida'])).limit(1)):
        raise error(409, 'cambio_en_curso', 'La cuenta ya tiene un cambio de permisos pendiente')
    if data.nombre is not None:
        usuario.nombre = data.nombre
    if data.email is not None:
        usuario.email = data.email
    if data.rol is not None:
        usuario.rol = RolUsuario(data.rol)
    if data.activo is not None:
        usuario.activo = data.activo
    if data.recibir_notificaciones_email is not None:
        usuario.recibir_notificaciones_email = data.recibir_notificaciones_email

    # Cambio de contraseña opcional
    if data.nueva_password:
        from app.utils.security import hash_password_async
        from app.services.auth_service import invalidar_todas, auditar
        from app.services.restauracion_service import validar_password_reemision
        await validar_password_reemision(db, usuario, data.nueva_password)
        usuario.password_hash = await hash_password_async(data.nueva_password)
        usuario.debe_cambiar_password = True
        from app.services.notificacion_service import cancelar_bienvenidas
        await cancelar_bienvenidas(db, usuario)
        await invalidar_todas(db, usuario)
        from app.services.restauracion_service import registrar_reemision
        await registrar_reemision(db, usuario, operador=f'usuario:{current_user.id}',
                                 referencia=f'restablecimiento-admin:{current_user.id}:{usuario.auth_version}')
        auditar(db, usuario, 'password_provisoria_restablecida', actor=current_user)

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

    usuario.revision_admin += 1
    await db.commit()
    await db.refresh(usuario)
    return await con_catedras(db, usuario)


@router.delete("/{usuario_id}", response_model=UsuarioRetiroResponse)
async def retirar_usuario(
    usuario_id: int,
    current_user: Usuario = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    clave: str | None = Header(default=None, alias='Idempotency-Key'),
    revision_esperada: int | None = None,
):
    """Retira con revocación previa y conserva la identidad de auditoría."""
    current_user = await exigir_gestion(db, current_user)
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

    if usuario.inventario_consola == 'asignada' and (not clave or revision_esperada is None):
        raise error(422, 'revision_o_clave_ausente', 'El retiro nativo requiere revisión y clave idempotente')
    result = await solicitar_cambio(db, usuario_objetivo_id=usuario.id, catedra_id=None,
        accion='retirar', cambios={'activo': False},
        revision_esperada=revision_esperada or usuario.revision_admin,
        actor=current_user, clave=clave or 'local:' + str(uuid4()))
    await db.commit()
    return respuesta_decision(result)
