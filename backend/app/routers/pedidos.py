from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.services.email_service import (
    obtener_emails_administradores,
    enviar_email_nuevo_pedido,
    enviar_email_pedido_ajuste,
    enviar_email_pedido_rechazado,
)
from app.models.pedido import (
    Pedido,
    PedidoHistorial,
    EstadoPedido,
    TipoPedido,
    ModeloServicio,
    VigenciaTipo,
)
from app.models.recurso_template import RecursoTemplate
from app.models.catedra import Catedra
from app.models.usuario import Usuario, RolUsuario
from app.routers.auth import get_current_user, require_admin
from app.schemas.pedido import (
    PedidoCreate,
    PedidoAprobar,
    PedidoEvaluacion,
    PedidoSolicitarAjuste,
    PedidoReenviar,
    PedidoCancelar,
    CapacidadLiberada,
    PedidoRechazar,
    PedidoRevertir,
    PedidoResponse,
    PedidoDetalleResponse,
    PedidoRevertidoResponse,
)
from app.schemas.servicio import ServicioResponse, OrdenServicioRequest
from app.services import capacidad_service
from app.services.acceso_service import catedras_visibles, es_visible
from app.services.orquestacion_service import reintentar_despliegue
from app.services.pedido_service import (
    crear_pedido,
    dar_de_baja_pedido,
    rechazar_pedido,
    revertir_aprobacion,
    solicitar_ajuste,
    reenviar_pedido,
    cancelar_pedido,
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
    from app.services.operacion_service import anexar_pedidos
    return await anexar_pedidos(db, list(result.scalars().all()))


@router.get("/estados")
async def obtener_estados(current_user: Usuario = Depends(get_current_user)):
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

    from app.services.operacion_service import anexar_pedidos
    await anexar_pedidos(db, [pedido])
    return pedido


@router.post("/", status_code=201)
async def crear_nuevo_pedido(data: PedidoCreate, clave: str = Header(alias='Idempotency-Key'),
    current_user: Usuario = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.services.solicitud_service import crear
    from app.utils.responses import respuesta_decision
    try:
        result = await crear(db, actor=current_user, payload=data, clave=clave)
        await db.commit()
        return respuesta_decision(result)
    except Exception:
        await db.rollback()
        raise


@router.get("/{pedido_id}/evaluacion")
async def evaluacion_get_retirada(pedido_id: int, current_user: Usuario = Depends(require_admin)):
    raise HTTPException(status_code=405, detail="Evaluá la selección efectiva mediante POST", headers={"Allow": "POST"})


@router.post("/{pedido_id}/evaluacion")
async def evaluar_seleccion(pedido_id: int, data: PedidoEvaluacion,
    current_user: Usuario = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    from app.services.evaluacion_service import evaluar
    from fastapi.responses import JSONResponse
    result = await evaluar(db, pedido_id, actor=current_user, payload=data)
    return JSONResponse(result, headers={'Cache-Control': 'no-store'})


@router.post("/{pedido_id}/aprobar")
async def aprobar(pedido_id: int, data: PedidoAprobar,
    clave: str = Header(alias='Idempotency-Key'),
    current_user: Usuario = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    from app.services.admision_service import aprobar as admitir
    from app.utils.responses import respuesta_decision
    try:
        result = await admitir(db, pedido_id, actor=current_user, payload=data, clave=clave)
        await db.commit()
        return respuesta_decision(result)
    except Exception:
        await db.rollback()
        raise


@router.post("/{pedido_id}/solicitar-ajuste")
async def solicitar_ajuste_endpoint(pedido_id: int, data: PedidoSolicitarAjuste,
    clave: str = Header(alias='Idempotency-Key'),
    current_user: Usuario = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    from app.utils.responses import respuesta_decision
    try:
        result = await solicitar_ajuste(db, pedido_id, current_user, data.observaciones, clave=clave)
        await db.commit()
        return respuesta_decision(result)
    except Exception:
        await db.rollback()
        raise


async def _resolver_solicitud(db, pedido_id, user, *, tipo, data, clave):
    from app.services.solicitud_service import resolver
    from app.utils.responses import respuesta_decision
    try:
        result = await resolver(db, pedido_id, actor=user, tipo=tipo, payload=data, clave=clave)
        await db.commit()
        return respuesta_decision(result)
    except Exception:
        await db.rollback()
        raise


@router.post("/{pedido_id}/reenviar")
async def reenviar_pedido_endpoint(pedido_id: int, data: PedidoReenviar, clave: str = Header(alias='Idempotency-Key'),
    current_user: Usuario = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return await _resolver_solicitud(db, pedido_id, current_user, tipo='reenviar', data=data, clave=clave)


@router.post("/{pedido_id}/cancelar")
async def cancelar_pedido_endpoint(pedido_id: int, data: PedidoCancelar, clave: str = Header(alias='Idempotency-Key'),
    current_user: Usuario = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return await _resolver_solicitud(db, pedido_id, current_user, tipo='cancelar', data=data, clave=clave)


@router.post("/{pedido_id}/rechazar")
async def rechazar(pedido_id: int, data: PedidoRechazar, clave: str = Header(alias='Idempotency-Key'),
    current_user: Usuario = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return await _resolver_solicitud(db, pedido_id, current_user, tipo='rechazar', data=data, clave=clave)


@router.post("/{pedido_id}/revertir-aprobacion")
async def revertir(pedido_id: int, data: PedidoRevertir,
    clave: str = Header(alias='Idempotency-Key'),
    current_user: Usuario = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    from app.utils.responses import respuesta_decision
    try:
        result = await revertir_aprobacion(db, pedido_id, current_user, data.motivo, clave=clave)
        await db.commit()
        return respuesta_decision(result)
    except Exception:
        await db.rollback()
        raise


@router.patch("/{pedido_id}/estado")
async def cambiar_estado_pedido_retirado(
    pedido_id: int,
    current_user: Usuario = Depends(get_current_user),
):
    """Los estados solo cambian mediante decisiones y operaciones nombradas."""
    raise HTTPException(status_code=405, detail="Usá una acción nombrada del pedido", headers={"Allow": "GET"})


@router.delete("/{pedido_id}")
async def dar_de_baja(pedido_id: int, clave: str = Header(alias='Idempotency-Key'),
    current_user: Usuario = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    from app.utils.responses import respuesta_decision
    try:
        result = await dar_de_baja_pedido(db, pedido_id, current_user, clave=clave)
        await db.commit()
        return respuesta_decision(result)
    except Exception:
        await db.rollback()
        raise


@router.post("/{pedido_id}/reintentar")
async def reintentar(pedido_id: int, body: OrdenServicioRequest = OrdenServicioRequest(),
    clave: str = Header(alias='Idempotency-Key'), current_user: Usuario = Depends(require_admin),
    db: AsyncSession = Depends(get_db)):
    from app.utils.responses import respuesta_decision
    try:
        result = await reintentar_despliegue(db, pedido_id, current_user, clave=clave, motivo=body.motivo)
        await db.commit()
        return respuesta_decision(result)
    except Exception:
        await db.rollback()
        raise
