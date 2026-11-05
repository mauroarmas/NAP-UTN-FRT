from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.usuario import Usuario
from app.routers.auth import require_admin
from app.schemas.evidencia import MAX_BYTES, parse_document
from app.services import evidencia_service
from app.utils.errors import error
from app.utils.clock import db_utc

router = APIRouter(prefix='/evidencias', tags=['Evidencias'])


@router.post('')
async def registrar_evidencia(request: Request, current_user: Usuario = Depends(require_admin),
                             key: str = Header(alias='Idempotency-Key'), db: AsyncSession = Depends(get_db)):
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > MAX_BYTES:
            raise error(413, 'contenido_demasiado_grande', 'La evidencia supera 64 KiB')
    document = parse_document(bytes(raw))
    try:
        result = await evidencia_service.registrar(db, document, usuario=current_user, clave=key)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    headers = {'Cache-Control': 'no-store'}
    if result.replayed:
        headers['Idempotency-Replayed'] = 'true'
    return JSONResponse(status_code=result.status_code, content=result.resultado, headers=headers)


@router.get('/{evidencia_id}')
async def obtener_evidencia(evidencia_id: UUID, current_user: Usuario = Depends(require_admin),
                           db: AsyncSession = Depends(get_db)):
    entry, document = await evidencia_service.obtener(db, evidencia_id)
    return JSONResponse(content={'evidencia_ref': str(entry.id), 'tipo': entry.tipo,
        'sha256': entry.sha256, 'documento': document, 'registrada_por': entry.registrada_por,
        'registrada_at': db_utc(entry.registrada_at).isoformat().replace('+00:00', 'Z')},
        headers={'Cache-Control': 'no-store'})
