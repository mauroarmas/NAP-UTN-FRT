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
from app.schemas.servicio import ServicioResponse, DesplegarRequest
from app.services.orquestacion_service import reintentar_despliegue
from app.services.pedido_service import (
    crear_pedido,
    cambiar_estado,
    dar_de_baja_pedido,
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
    query = excluir_dados_de_baja(select(Pedido), Pedido).order_by(
        Pedido.created_at.desc()
    )

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
    pedido = vigente_o_404(result.scalar_one_or_none(), "Pedido no encontrado")

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
        .options(selectinload(Pedido.historial))
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
