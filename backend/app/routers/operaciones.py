from uuid import UUID
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.routers.auth import get_current_user
from app.services.operacion_service import obtener, presentar, listar

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
