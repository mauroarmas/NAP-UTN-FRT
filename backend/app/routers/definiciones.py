from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.routers.auth import get_current_user, require_admin
from app.schemas.definicion import DefinicionCreate, AccionDefinicion, RetirarDefinicion, parse_manifest
from app.services import catalogo_service
from app.utils.errors import error
from app.utils.responses import respuesta_decision

router = APIRouter(prefix='/definiciones', tags=['Definiciones de servicio'])


async def responder(db, decision):
    try:
        result = await decision
        await db.commit()
        return respuesta_decision(result)
    except Exception:
        await db.rollback()
        raise


@router.get('')
async def listar(modelo_servicio: Literal['iaas', 'paas', 'saas'] | None = None, incluir_no_publicadas: bool = False,
    actor=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return JSONResponse(await catalogo_service.listar(db, actor=actor, modelo=modelo_servicio,
        incluir_no_publicadas=incluir_no_publicadas), headers={'Cache-Control': 'no-store'})


@router.get('/{identity}')
async def obtener(identity: UUID, actor=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return JSONResponse(await catalogo_service.obtener(db, identity, actor=actor), headers={'Cache-Control': 'no-store'})


@router.post('', status_code=201)
async def crear(body: DefinicionCreate, clave: str = Header(alias='Idempotency-Key'), actor=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return await responder(db, catalogo_service.crear(db, actor=actor, data=body, clave=clave))


@router.put('/{identity}/manifest')
async def guardar(identity: UUID, request: Request, clave: str = Header(alias='Idempotency-Key'), actor=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 262144:
            raise error(413, 'contenido_demasiado_grande', 'El manifiesto supera 256 KiB')
    manifest = parse_manifest(bytes(raw))
    return await responder(db, catalogo_service.guardar_manifest(db, identity, actor=actor, manifest=manifest, clave=clave))


@router.post('/{identity}/validar')
async def validar(identity: UUID, body: AccionDefinicion, clave: str = Header(alias='Idempotency-Key'), actor=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return await responder(db, catalogo_service.transicionar(db, identity, actor=actor, accion='validar', payload=body.model_dump(), clave=clave))


@router.post('/{identity}/publicar')
async def publicar(identity: UUID, body: AccionDefinicion, clave: str = Header(alias='Idempotency-Key'), actor=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return await responder(db, catalogo_service.transicionar(db, identity, actor=actor, accion='publicar', payload=body.model_dump(), clave=clave))


@router.post('/{identity}/retirar')
async def retirar(identity: UUID, body: RetirarDefinicion, clave: str = Header(alias='Idempotency-Key'), actor=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return await responder(db, catalogo_service.transicionar(db, identity, actor=actor, accion='retirar', payload=body.model_dump(), clave=clave))


from app.schemas.ensayo import EnsayoCreate


@router.post('/{identity}/ensayos')
async def iniciar_ensayo(identity:UUID,body:EnsayoCreate,clave:str=Header(alias='Idempotency-Key'),actor=Depends(require_admin),db:AsyncSession=Depends(get_db)):
    from app.services.ensayo_service import iniciar
    return await responder(db,iniciar(db,identity,actor=actor,data=body,clave=clave))


from app.schemas.ensayo import PublicarOferta


@router.post('/{identity}/publicar-oferta')
async def publicar_oferta(identity:UUID,body:PublicarOferta,clave:str=Header(alias='Idempotency-Key'),actor=Depends(require_admin),db:AsyncSession=Depends(get_db)):
    return await responder(db,catalogo_service.publicar_oferta(db,identity,actor=actor,data=body,clave=clave))


@router.get('/{identity}/ensayos')
async def ensayos_definicion(identity:UUID,actor=Depends(require_admin),db:AsyncSession=Depends(get_db)):
    from app.models.ensayo_preparacion import EnsayoPreparacion
    from app.services.ensayo_service import presentar
    from sqlalchemy import select
    values=(await db.scalars(select(EnsayoPreparacion).where(EnsayoPreparacion.definicion_id==identity).order_by(EnsayoPreparacion.creado_at.desc()))).all()
    return JSONResponse({'items':[presentar(v) for v in values]},headers={'Cache-Control':'no-store'})
