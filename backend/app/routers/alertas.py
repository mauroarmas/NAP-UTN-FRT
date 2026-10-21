"""Proyecciones DB con alcance vigente; los errores de entrega son administrativos."""
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.incidente import Incidente
from app.models.notificacion import Notificacion
from app.models.servicio import Servicio
from app.models.usuario import RolUsuario
from app.routers.auth import get_current_user, require_admin
from app.services.acceso_service import catedras_visibles

router = APIRouter(prefix='/alertas', tags=['Alertas y avisos'])


def respuesta(rows):
    return JSONResponse(jsonable_encoder(rows), headers={'Cache-Control': 'no-store'})


@router.get('/correo')
async def correo(estado: Literal['pendiente','enviando','enviada','fallida','cancelada'] | None = None,
    limit: int = Query(default=100, ge=1, le=500), actor=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    query = select(Notificacion).where(Notificacion.canal == 'email')
    if estado: query = query.where(Notificacion.estado == estado)
    rows = (await db.scalars(query.order_by(Notificacion.created_at.desc(), Notificacion.id).limit(limit))).all()
    fields = ['id','evento_clave','destinatario_usuario_id','catedra_id','servicio_id','estado',
        'intentos','ultimo_error','proximo_intento_at','created_at','enviada_at']
    return respuesta([{key: getattr(row,key) for key in fields} for row in rows])


@router.get('/avisos')
async def avisos(servicio_id: int | None = None, limit: int = Query(default=100, ge=1, le=500),
    actor=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    query = select(Notificacion).where(Notificacion.canal == 'portal', Notificacion.destinatario_usuario_id == actor.id,
        Notificacion.servicio_id.is_not(None))
    if actor.rol != RolUsuario.ADMIN:
        query = query.where(Notificacion.catedra_id.in_(await catedras_visibles(db, actor)))
    if servicio_id is not None: query = query.where(Notificacion.servicio_id == servicio_id)
    rows = (await db.scalars(query.order_by(Notificacion.created_at.desc(), Notificacion.id).limit(limit))).all()
    return respuesta([{'id': row.id, 'servicio_id': row.servicio_id, 'catedra_id': row.catedra_id,
        'tipo': row.payload.get('tipo'), 'asunto': row.payload.get('asunto'), 'texto': row.payload.get('texto'),
        'created_at': row.created_at} for row in rows])


@router.get('')
async def listar(servicio_id: int | None = None, estado: Literal['abierto','resuelto'] | None = None,
    limit: int = Query(default=100, ge=1, le=500), actor=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    query = select(Incidente, Servicio.catedra_id).join(Servicio, Servicio.id == Incidente.servicio_id)
    if actor.rol != RolUsuario.ADMIN:
        query = query.where(Servicio.catedra_id.in_(await catedras_visibles(db, actor)))
    if servicio_id is not None: query = query.where(Incidente.servicio_id == servicio_id)
    if estado: query = query.where(Incidente.estado == estado)
    rows = (await db.execute(query.order_by(Incidente.abierto_at.desc(), Incidente.id).limit(limit))).all()
    fields = ['id','servicio_id','tipo','estado','abierto_at','ultima_observacion_at','resuelto_at','regla_version']
    return respuesta([{**{key: getattr(row,key) for key in fields}, 'catedra_id': category} for row, category in rows])
