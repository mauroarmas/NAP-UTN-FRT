from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.catedra import Catedra
from app.models.pedido import Pedido, PedidoHistorial, EstadoPedido, TipoPedido
from app.models.recurso_template import RecursoTemplate
from app.models.usuario import Usuario, RolUsuario
from app.routers.auth import get_current_user, require_admin
from app.schemas.pedido import (
    PedidoCreate,
    PedidoCambiarEstado,
    PedidoAprobar,
    CapacidadLiberada,
    PedidoRechazar,
    PedidoRevertir,
    PedidoResponse,
    PedidoDetalleResponse,
    PedidoRevertidoResponse,
)
from app.schemas.servicio import ServicioResponse, DesplegarRequest
from app.services import capacidad_service
from app.services.acceso_service import catedras_visibles, es_visible
from app.services.orquestacion_service import reintentar_despliegue
from app.services.pedido_service import (
    crear_pedido,
    cambiar_estado,
    dar_de_baja_pedido,
    aprobar_pedido,
    rechazar_pedido,
    revertir_aprobacion,
    TRANSICIONES_VALIDAS,
)
from app.utils.soft_delete import excluir_dados_de_baja, vigente_o_404

router = APIRouter(prefix="/pedidos", tags=["Pedidos"])


@router.get("/", response_model=list[PedidoResponse])
async def listar_pedidos(
    estado: str | None = Query(None, description="Filtrar por estado"),
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Lista pedidos vigentes. Admin ve todos, cátedra ve solo los suyos."""
    # `selectinload` de la cátedra no es una optimización: `PedidoResponse` la
    # incluye anidada, y una relación de carga diferida resuelta durante la
    # serialización revienta en contexto async.
    query = (
        excluir_dados_de_baja(select(Pedido), Pedido)
        .options(selectinload(Pedido.catedra))
        .order_by(Pedido.created_at.desc())
    )

    # Alcance: el conjunto de cátedras de la persona (todas, si es admin)
    if current_user.rol != RolUsuario.ADMIN:
        query = query.where(
            Pedido.catedra_id.in_(await catedras_visibles(db, current_user))
        )

    # Filtrar por estado
    if estado:
        try:
            estado_enum = EstadoPedido(estado)
            query = query.where(Pedido.estado == estado_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Estado inválido: {estado}")

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/estados")
async def obtener_estados():
    """Devuelve la máquina de estados con las transiciones válidas."""
    return {
        "estados": [e.value for e in EstadoPedido],
        "transiciones": {
            k.value: [v.value for v in vals]
            for k, vals in TRANSICIONES_VALIDAS.items()
        },
    }


@router.get("/{pedido_id}", response_model=PedidoDetalleResponse)
async def obtener_pedido(
    pedido_id: int,
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Obtiene un pedido con su historial completo."""
    result = await db.execute(
        select(Pedido)
        .options(selectinload(Pedido.historial), selectinload(Pedido.catedra))
        .where(Pedido.id == pedido_id)
    )
    pedido = vigente_o_404(result.scalar_one_or_none(), "Pedido no encontrado")

    if not await es_visible(db, current_user, pedido.catedra_id):
        raise HTTPException(status_code=403, detail="Sin permisos para ver este pedido")

    return pedido


@router.post("/", response_model=PedidoResponse, status_code=201)
async def crear_nuevo_pedido(
    data: PedidoCreate,
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Crea un pedido de servicio.

    No se rechaza por consumo acumulado de la cátedra: eso lo resuelve el
    administrador al aprobarlo, con la capacidad real del clúster a la vista.
    """
    pedido = await crear_pedido(
        db=db,
        template_id=data.template_id,
        usuario=current_user,
        catedra_id=data.catedra_id,
        parametros_extra=data.parametros_extra,
    )
    # Se relee con la cátedra cargada: la respuesta la incluye anidada y
    # resolverla al serializar fallaría.
    result = await db.execute(
        select(Pedido)
        .options(selectinload(Pedido.catedra))
        .where(Pedido.id == pedido.id)
    )
    return result.scalar_one()


@router.get("/{pedido_id}/evaluacion")
async def evaluar_pedido(
    pedido_id: int,
    current_user: Usuario = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Todo lo que el administrador necesita para decidir sobre un pedido.

    Incluye el `capacidad_token`: hay que devolverlo al aprobar, y si la
    capacidad cambió en el medio la aprobación se rechaza con 409 en lugar de
    resolverse sobre números viejos.
    """
    pedido = vigente_o_404(await db.get(Pedido, pedido_id), "Pedido no encontrado")
    template = await db.get(RecursoTemplate, pedido.template_id)
    catedra = await db.get(Catedra, pedido.catedra_id)

    try:
        estado = await capacidad_service.panorama(db)
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="No se pudo consultar la capacidad del clúster Proxmox",
        )

    costo = (
        {"vcpus": 0, "ram_mb": 0, "storage_gb": 0}
        if pedido.tipo == TipoPedido.RENOVACION
        else capacidad_service.costo_de(template)
    )

    return {
        "pedido": {
            "id": pedido.id,
            "tipo": pedido.tipo.value,
            "catedra": {"id": catedra.id, "nombre": catedra.nombre},
        },
        "costo": costo,
        "consumo_catedra": await capacidad_service.consumo_de_catedra(
            db, pedido.catedra_id
        ),
        "capacidad": estado,
        "libre_si_aprueba": {
            k: estado["libre"][k] - costo[k] for k in costo
        },
        "excede_capacidad": capacidad_service.excede(estado["libre"], costo),
        "capacidad_token": estado["capacidad_token"],
    }


@router.post("/{pedido_id}/aprobar", response_model=PedidoDetalleResponse)
async def aprobar(
    pedido_id: int,
    data: PedidoAprobar,
    current_user: Usuario = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Aprueba un pedido y reserva su capacidad en el acto.

    Códigos: 200 aprobado · 400 excede la capacidad y falta justificación ·
    409 token de capacidad desactualizado, o el pedido no está en solicitado.
    """
    vigente_o_404(await db.get(Pedido, pedido_id), "Pedido no encontrado")
    pedido = await aprobar_pedido(
        db=db,
        pedido_id=pedido_id,
        admin=current_user,
        capacidad_token=data.capacidad_token,
        justificacion_capacidad=data.justificacion_capacidad,
    )
    result = await db.execute(
        select(Pedido)
        .options(selectinload(Pedido.historial), selectinload(Pedido.catedra))
        .where(Pedido.id == pedido.id)
    )
    return result.scalar_one()


@router.post("/{pedido_id}/rechazar", response_model=PedidoDetalleResponse)
async def rechazar(
    pedido_id: int,
    data: PedidoRechazar,
    current_user: Usuario = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Rechaza un pedido con un motivo que la cátedra solicitante puede ver."""
    vigente_o_404(await db.get(Pedido, pedido_id), "Pedido no encontrado")
    pedido = await rechazar_pedido(
        db=db, pedido_id=pedido_id, admin=current_user, motivo=data.motivo
    )
    result = await db.execute(
        select(Pedido)
        .options(selectinload(Pedido.historial), selectinload(Pedido.catedra))
        .where(Pedido.id == pedido.id)
    )
    return result.scalar_one()


@router.post("/{pedido_id}/revertir-aprobacion", response_model=PedidoRevertidoResponse)
async def revertir(
    pedido_id: int,
    data: PedidoRevertir,
    current_user: Usuario = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Deshace una aprobación antes del despliegue y libera su capacidad.

    Es una operación con nombre propio y no un cambio de estado a mano: mover el
    estado sin liberar la reserva dejaría capacidad huérfana, que es lo que
    `PATCH /estado` sigue impidiendo.

    Códigos: 200 revertido, con la capacidad que volvió · 400 falta el motivo ·
    403 sin permisos de administrador · 404 pedido inexistente o dado de baja ·
    409 con un código propio por caso: `pedido_no_aprobado`,
    `despliegue_en_curso`, `reserva_ya_vencida` o `ya_revertido`.
    """
    vigente_o_404(await db.get(Pedido, pedido_id), "Pedido no encontrado")
    pedido, liberado = await revertir_aprobacion(
        db=db, pedido_id=pedido_id, admin=current_user, motivo=data.motivo
    )
    result = await db.execute(
        select(Pedido)
        .options(selectinload(Pedido.historial), selectinload(Pedido.catedra))
        .where(Pedido.id == pedido.id)
    )
    respuesta = PedidoRevertidoResponse.model_validate(result.scalar_one())
    respuesta.capacidad_liberada = CapacidadLiberada(**liberado)
    return respuesta


@router.patch("/{pedido_id}/estado", response_model=PedidoDetalleResponse)
async def cambiar_estado_pedido(
    pedido_id: int,
    data: PedidoCambiarEstado,
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cambia el estado de un pedido. Valida la máquina de estados."""
    vigente_o_404(await db.get(Pedido, pedido_id), "Pedido no encontrado")

    pedido = await cambiar_estado(
        db=db,
        pedido_id=pedido_id,
        nuevo_estado_str=data.nuevo_estado,
        usuario=current_user,
        comentario=data.comentario,
        motivo_rechazo=data.motivo_rechazo,
    )

    # Recargar con historial
    result = await db.execute(
        select(Pedido)
        .options(selectinload(Pedido.historial), selectinload(Pedido.catedra))
        .where(Pedido.id == pedido.id)
    )
    return result.scalar_one()


@router.delete("/{pedido_id}")
async def dar_de_baja(
    pedido_id: int,
    current_user: Usuario = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Da de baja lógicamente un pedido, en cualquier estado.

    El registro no se borra: permanece para reconstruir el consumo histórico de
    la cátedra. No ejecuta ninguna operación contra Proxmox.

    Códigos: 200 baja exitosa (o ya estaba dada de baja, idempotente) ·
    403 sin permisos de administrador · 404 pedido inexistente ·
    409 el pedido tiene un servicio vigente que debe darse de baja primero.
    """
    return await dar_de_baja_pedido(db=db, pedido_id=pedido_id, admin=current_user)


@router.post("/{pedido_id}/reintentar", response_model=ServicioResponse)
async def reintentar(
    pedido_id: int,
    body: DesplegarRequest = DesplegarRequest(),
    current_user: Usuario = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Reintenta el despliegue de un pedido que quedó en ERROR.

    Ejecuta la transición ERROR → EN_DESPLIEGUE → ACTIVO (o ERROR de nuevo).
    Es pseudo-idempotente: reutiliza el VMID reservado o adopta el contenedor si
    quedó creado por un fallo parcial, de modo que no duplica recursos.

    Códigos: 200 reintento exitoso · 403 sin permisos de administrador ·
    404 pedido inexistente o dado de baja · 409 el pedido no está en ERROR ·
    502 la infraestructura volvió a fallar (el pedido regresa a ERROR).
    """
    return await reintentar_despliegue(
        db=db,
        pedido_id=pedido_id,
        admin=current_user,
        node=body.node,
        storage=body.storage,
    )
