from fastapi import APIRouter, Depends, Header, Path
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.routers.auth import get_current_user, require_admin
from app.schemas.calendario import CalendarioEscritura
from app.services import calendario_service
from app.utils.responses import respuesta_decision

router = APIRouter(prefix='/calendarios', tags=['Calendario lectivo'])


@router.get('/{anio}')
@router.get('/{anio}/periodos')
async def obtener(anio: int = Path(ge=1900, le=9998), current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return JSONResponse(await calendario_service.obtener(db, anio), headers={'Cache-Control': 'no-store'})


@router.put('/{anio}')
async def guardar(body: CalendarioEscritura, anio: int = Path(ge=1900, le=9998),
    clave: str = Header(alias='Idempotency-Key'), current_user=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    try:
        result = await calendario_service.guardar(db, anio, body, actor=current_user, clave=clave)
        await db.commit()
        return respuesta_decision(result)
    except Exception:
        await db.rollback()
        raise
