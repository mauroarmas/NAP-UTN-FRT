from uuid import UUID
from typing import Annotated
from fastapi import APIRouter,Depends,Header,Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.routers.auth import require_admin
from app.routers.definiciones import responder
from app.schemas.biblioteca import Busqueda,IncorporacionCreate,IncorporacionEdit
from app.schemas.biblioteca_common import Paginacion
from app.services import biblioteca_service

router=APIRouter(prefix='/biblioteca',tags=['Biblioteca de aplicaciones'])


@router.get('/aplicaciones')
async def buscar(filters:Annotated[Busqueda,Query()],actor=Depends(require_admin),db:AsyncSession=Depends(get_db)):
    return JSONResponse(await biblioteca_service.buscar(db,actor=actor,filters=filters),headers={'Cache-Control':'no-store'})


@router.get('/categorias')
async def categorias(actor=Depends(require_admin),db:AsyncSession=Depends(get_db)):
    return JSONResponse(await biblioteca_service.categorias(db,actor=actor),headers={'Cache-Control':'no-store'})


@router.post('/incorporaciones')
async def incorporar(body:IncorporacionCreate,clave:str=Header(alias='Idempotency-Key'),actor=Depends(require_admin),db:AsyncSession=Depends(get_db)):
    return await responder(db,biblioteca_service.incorporar(db,actor=actor,data=body,clave=clave))


@router.get('/incorporaciones')
async def listar(filters:Annotated[Paginacion,Query()],actor=Depends(require_admin),db:AsyncSession=Depends(get_db)):
    return JSONResponse(await biblioteca_service.listar(db,actor=actor,filters=filters),headers={'Cache-Control':'no-store'})


@router.get('/incorporaciones/{identity}')
async def obtener(identity:UUID,actor=Depends(require_admin),db:AsyncSession=Depends(get_db)):
    row=await biblioteca_service.obtener(db,identity,actor=actor)
    from sqlalchemy import select
    from app.models.definicion_servicio import DefinicionServicio
    definitions=(await db.scalars(select(DefinicionServicio).where(DefinicionServicio.incorporacion_id==identity).order_by(DefinicionServicio.created_at))).all()
    return JSONResponse({**biblioteca_service.present(row),'definiciones':[{'id':str(d.id),'codigo':d.codigo,'version':d.version,'revision':d.revision,'estado':d.estado} for d in definitions]},headers={'Cache-Control':'no-store'})


@router.patch('/incorporaciones/{identity}')
async def editar(identity:UUID,body:IncorporacionEdit,clave:str=Header(alias='Idempotency-Key'),actor=Depends(require_admin),db:AsyncSession=Depends(get_db)):
    return await responder(db,biblioteca_service.editar(db,identity,actor=actor,data=body,clave=clave))


from app.schemas.ensayo import RevisionBiblioteca
from app.services import ensayo_service
from app.services import preparacion_simple_service as preparacion
from app.schemas.definicion import AccionDefinicion
from app.schemas.ensayo import ConfirmarFuncionamiento
from app.schemas.preparacion_simple import PublicarAplicacion, PrepararAplicacion


@router.get('/incorporaciones/{identity}/preparacion')
async def consultar_preparacion(identity:UUID,actor=Depends(require_admin),db:AsyncSession=Depends(get_db)):
    return JSONResponse(await preparacion.estado(db,identity,actor=actor),headers={'Cache-Control':'no-store'})


@router.post('/incorporaciones/{identity}/preparar')
async def preparar(identity:UUID,body:PrepararAplicacion,clave:str=Header(alias='Idempotency-Key'),actor=Depends(require_admin),db:AsyncSession=Depends(get_db)):
    return await responder(db,preparacion.preparar(db,identity,actor=actor,clave=clave,data=body))


@router.post('/incorporaciones/{identity}/agregar')
async def agregar(identity:UUID,body:PublicarAplicacion,clave:str=Header(alias='Idempotency-Key'),actor=Depends(require_admin),db:AsyncSession=Depends(get_db)):
    return await responder(db,preparacion.preparar(db,identity,actor=actor,clave=clave,data=body,automatico=True))


@router.post('/incorporaciones/{identity}/confirmar-funcionamiento')
async def confirmar_funcionamiento(identity:UUID,body:ConfirmarFuncionamiento,clave:str=Header(alias='Idempotency-Key'),actor=Depends(require_admin),db:AsyncSession=Depends(get_db)):
    return await responder(db,preparacion.confirmar(db,identity,actor=actor,funciona=body.funciona,clave=clave))


@router.post('/incorporaciones/{identity}/publicar')
async def publicar(identity:UUID,body:PublicarAplicacion,clave:str=Header(alias='Idempotency-Key'),actor=Depends(require_admin),db:AsyncSession=Depends(get_db)):
    return await responder(db,preparacion.publicar(db,identity,actor=actor,data=body,clave=clave))


@router.post('/incorporaciones/{identity}/eliminar')
async def eliminar_preparacion(identity:UUID,body:AccionDefinicion,clave:str=Header(alias='Idempotency-Key'),actor=Depends(require_admin),db:AsyncSession=Depends(get_db)):
    return await responder(db,preparacion.eliminar(db,identity,actor=actor,clave=clave))


@router.post('/incorporaciones/{identity}/definicion')
async def crear_revision(identity:UUID,body:RevisionBiblioteca,clave:str=Header(alias='Idempotency-Key'),actor=Depends(require_admin),db:AsyncSession=Depends(get_db)):
    return await responder(db,ensayo_service.crear_revision(db,identity,actor=actor,data=body,clave=clave))
