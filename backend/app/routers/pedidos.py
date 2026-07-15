from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.pedido import Pedido, PedidoHistorial, EstadoPedido
from app.models.usuario import Usuario, RolUsuario
from app.routers.auth import get_current_user, require_admin
from app.schemas.pedido import (
    PedidoCreate,
    PedidoCambiarEstado,
    PedidoResponse,
    PedidoDetalleResponse,
)
from app.services.pedido_service import (
    crear_pedido,
    cambiar_estado,
    TRANSICIONES_VALIDAS,
)

router = APIRouter(prefix="/pedidos", tags=["Pedidos"])


@router.get("/", response_model=list[PedidoResponse])
async def listar_pedidos(
    estado: str | None = Query(None, description="Filtrar por estado"),
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Lista pedidos. Admin ve todos, cátedra ve solo los suyos."""
    query = select(Pedido).order_by(Pedido.created_at.desc())

    # Filtrar por rol
    if current_user.rol != RolUsuario.ADMIN:
        query = query.where(Pedido.catedra_id == current_user.catedra_id)

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
        .options(selectinload(Pedido.historial))
        .where(Pedido.id == pedido_id)
    )
    pedido = result.scalar_one_or_none()

    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")

    # Verificar permisos
    if (
        current_user.rol != RolUsuario.ADMIN
        and pedido.catedra_id != current_user.catedra_id
    ):
        raise HTTPException(status_code=403, detail="Sin permisos para ver este pedido")

    return pedido


@router.post("/", response_model=PedidoResponse, status_code=201)
async def crear_nuevo_pedido(
    data: PedidoCreate,
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Crea un nuevo pedido de servicio. Valida cuotas automáticamente."""
    pedido = await crear_pedido(
        db=db,
        template_id=data.template_id,
        usuario=current_user,
        parametros_extra=data.parametros_extra,
    )
    return pedido


@router.patch("/{pedido_id}/estado", response_model=PedidoDetalleResponse)
async def cambiar_estado_pedido(
    pedido_id: int,
    data: PedidoCambiarEstado,
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cambia el estado de un pedido. Valida la máquina de estados."""
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
        .options(selectinload(Pedido.historial))
        .where(Pedido.id == pedido.id)
    )
    return result.scalar_one()
