"""Estado de las identidades individuales de consola para administración (feature 022). Nunca expone credenciales."""
from fastapi import APIRouter, Depends, Header, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.identidad_consola import IdentidadConsola
from app.models.usuario import Usuario
from app.routers.auth import require_admin
from app.services import identidad_consola_service
from app.utils.errors import error

router = APIRouter(prefix='/admin/identidades-consola', tags=['Identidades de consola'])


def proyectar(fila, usuario):
    """Sólo lo necesario para operar: ni la identidad técnica, ni la contraseña, ni su cifrado."""
    return {'usuario_id': fila.usuario_id, 'nombre': usuario.nombre if usuario else None,
            'estado': fila.estado, 'pools_aplicados': list(fila.pools_aplicados or []),
            'ultimo_error_seguro': fila.ultimo_error_seguro, 'reconciliada_at': fila.reconciliada_at}


@router.get('')
async def listar(estado: str | None = Query(default=None, pattern='^(en_preparacion|lista|con_error|retirada)$'),
                 current_user: Usuario = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    consulta = select(IdentidadConsola, Usuario).join(Usuario, Usuario.id == IdentidadConsola.usuario_id)\
        .order_by(IdentidadConsola.actualizada_at.desc()).limit(500)
    if estado:
        consulta = consulta.where(IdentidadConsola.estado == estado)
    filas = (await db.execute(consulta)).all()
    return JSONResponse(content=jsonable_encoder([proyectar(fila, usuario) for fila, usuario in filas]),
                        headers={'Cache-Control': 'no-store'})


@router.post('/{usuario_id}/reintentar', status_code=202)
async def reintentar(usuario_id: int, key: str = Header(alias='Idempotency-Key'),
                     current_user: Usuario = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    try:
        if not await identidad_consola_service.marcar_para_reintento(db, usuario_id):
            raise error(404, 'identidad_no_encontrada', 'La persona todavía no tiene identidad de consola')
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return JSONResponse(status_code=202, content={'usuario_id': usuario_id, 'estado': 'reintento_solicitado'},
                        headers={'Cache-Control': 'no-store'})
