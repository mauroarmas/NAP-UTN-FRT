from uuid import UUID
from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.operacion_infraestructura import OperacionInfraestructura
from app.models.usuario import Usuario
from app.routers.auth import get_current_user, require_admin
from app.schemas.operacion import ConsolaOperacionResponse
from app.schemas.servicio import OrdenServicioRequest
from app.services.operacion_service import obtener, presentar, listar, OPEN
from app.services.consola_operacion_service import consultar
from app.services.orquestacion_service import reintentar_despliegue
from app.utils.errors import error
from app.utils.responses import respuesta_decision

router = APIRouter(prefix='/operaciones', tags=['Operaciones'])


@router.get('')
async def listado(pedido_id: int | None = None, servicio_id: int | None = None, abiertas: bool = False,
    limit: int = Query(default=50, ge=1, le=100), cursor: str | None = Query(default=None, max_length=80),
    current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    data = await listar(db, usuario=current_user, pedido_id=pedido_id, servicio_id=servicio_id,
        abiertas=abiertas, limit=limit, cursor=cursor)
    return JSONResponse(data, headers={'Cache-Control': 'no-store'})


@router.get('/{operation_id}')
async def detalle(operation_id: UUID, current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    entry = await obtener(db, operation_id, usuario=current_user)
    return JSONResponse(presentar(entry), headers={'Cache-Control': 'no-store', 'Retry-After': '2'}
        if entry.estado in {'pendiente', 'en_curso', 'incierta'} else {'Cache-Control': 'no-store'})


@router.get('/{operation_id}/consola')
async def consultar_consola(
    operation_id: UUID,
    after: int | None = Query(default=None),
    before: int | None = Query(default=None),
    limit_bytes: int = Query(default=65536),
    through_seq: int | None = Query(default=None),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await consultar(
        db,
        operation_id,
        usuario=current_user,
        after=after,
        before=before,
        limit_bytes=limit_bytes,
        through_seq=through_seq,
    )
    serialized = ConsolaOperacionResponse.model_validate(data).model_dump(mode='json')
    return JSONResponse(serialized, headers={'Cache-Control': 'no-store'})


@router.post('/{operation_id}/reintentar')
async def reintentar_operacion(
    operation_id: UUID,
    body: OrdenServicioRequest = OrdenServicioRequest(),
    clave: str = Header(alias='Idempotency-Key'),
    current_user: Usuario = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    operation = await db.get(OperacionInfraestructura, operation_id)
    if operation is None:
        raise error(404, 'operacion_no_encontrada', 'Operación no encontrada')
    if operation.estado in OPEN or operation.estado == 'incierta':
        raise error(409, 'operacion_en_curso' if operation.estado in OPEN else 'reconciliacion_pendiente',
                    'Solo se reintenta una operación fallida confirmada')
    if operation.estado != 'fallida':
        raise error(409, 'estado_incompatible', 'Solo se reintenta una operación fallida revisada')
    if not operation.pedido_id:
        raise error(409, 'requiere_nueva_decision', 'La operación no corresponde a un pedido reintentable')

    try:
        result = await reintentar_despliegue(db, operation.pedido_id, current_user, clave=clave, motivo=body.motivo)
        await db.commit()
        return respuesta_decision(result)
    except Exception:
        await db.rollback()
        raise
