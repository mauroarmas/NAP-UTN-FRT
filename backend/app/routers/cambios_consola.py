from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.cambio_acceso_consola import CambioAccesoConsola
from app.models.usuario import Usuario
from app.routers.auth import require_admin
from app.schemas.cambios_consola import ConfirmarRevocacion, RegistrarFallo
from app.services import consola_access_service
from app.utils.errors import error

router = APIRouter(prefix='/admin/cambios-consola', tags=['Cambios de consola'])


def project(change):
    fields = ['accion', 'usuario_id', 'catedra_id', 'revision_esperada', 'identidad_nativa',
              'scopes_anteriores', 'scopes_propuestos', 'cambio_propuesto', 'estado',
              'solicitada_por', 'solicitada_at', 'ultimo_error_seguro', 'completada_at']
    return jsonable_encoder({'id': str(change.id), **{key: getattr(change, key) for key in fields},
                             'evidencia_ref': str(change.evidencia_id) if change.evidencia_id else None})


@router.get('')
async def listar(estado: str | None = Query(default=None, pattern='^(pendiente|revocacion_fallida|completado)$'),
                 current_user: Usuario = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    query = select(CambioAccesoConsola).order_by(CambioAccesoConsola.solicitada_at.desc()).limit(100)
    if estado:
        query = query.where(CambioAccesoConsola.estado == estado)
    entries = (await db.scalars(query)).all()
    return JSONResponse(content=[project(entry) for entry in entries], headers={'Cache-Control': 'no-store'})


@router.get('/{identity}')
async def detalle(identity: UUID, current_user: Usuario = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    entry = await db.get(CambioAccesoConsola, identity, populate_existing=True)
    if entry is None:
        raise error(404, 'cambio_no_encontrado', 'Trámite no encontrado')
    return JSONResponse(content=project(entry), headers={'Cache-Control': 'no-store'})


async def _complete(db, result):
    await db.commit()
    headers = {'Cache-Control': 'no-store'}
    if result.replayed:
        headers['Idempotency-Replayed'] = 'true'
    return JSONResponse(status_code=result.status_code, content=result.resultado, headers=headers)


@router.post('/{identity}/confirmar-revocacion')
async def confirmar(identity: UUID, data: ConfirmarRevocacion, current_user: Usuario = Depends(require_admin),
                    key: str = Header(alias='Idempotency-Key'), db: AsyncSession = Depends(get_db)):
    try:
        result = await consola_access_service.confirmar(db, identity, data.evidencia_ref, actor=current_user, clave=key)
        return await _complete(db, result)
    except Exception:
        await db.rollback()
        raise


@router.post('/{identity}/registrar-fallo')
async def registrar_fallo(identity: UUID, data: RegistrarFallo, current_user: Usuario = Depends(require_admin),
                          key: str = Header(alias='Idempotency-Key'), db: AsyncSession = Depends(get_db)):
    try:
        result = await consola_access_service.registrar_fallo(db, identity, data.motivo, actor=current_user, clave=key)
        return await _complete(db, result)
    except Exception:
        await db.rollback()
        raise
