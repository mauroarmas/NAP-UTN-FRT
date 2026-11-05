from uuid import UUID
from fastapi import APIRouter,Depends,Header,Query
from fastapi.responses import JSONResponse
from sqlalchemy import select,or_,and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.routers.auth import require_admin
from app.routers.definiciones import responder
from app.schemas.biblioteca_common import RevisionEsperada
from app.schemas.ensayo import ConfirmarEntradas,ComprobarEnsayo,DescartarEnsayo
from app.services import ensayo_service
from app.models.evento_ensayo import EventoEnsayo
from app.models.recurso_ensayo import RecursoEnsayo
from app.models.evento_seguridad import EventoSeguridad
from app.utils.secretos import configured_keyring
from app.utils.errors import error
from app.utils.clock import clock,db_utc

router=APIRouter(prefix='/ensayos',tags=['Ensayos de preparación'])


@router.get('/{identity}')
async def obtener(identity:UUID,actor=Depends(require_admin),db:AsyncSession=Depends(get_db)):
    row=await ensayo_service.obtener(db,identity,actor=actor)
    result=ensayo_service.presentar(row)
    resources=(await db.scalars(select(RecursoEnsayo).where(RecursoEnsayo.ensayo_id==identity))).all()
    from app.models.definicion_servicio import DefinicionServicio
    definition=await db.get(DefinicionServicio,row.definicion_id)
    result['definicion']={'id':str(definition.id),'codigo':definition.codigo,'version':definition.version,'revision':definition.revision,'estado':definition.estado}
    from app.models.operacion_ensayo import OperacionEnsayo
    operations=(await db.scalars(select(OperacionEnsayo).where(OperacionEnsayo.ensayo_id==identity).order_by(OperacionEnsayo.created_at.desc()).limit(50))).all()
    result['operaciones']=[{'id':str(o.id),'tipo':o.tipo,'estado':o.estado,'intento':o.intento,'error_codigo':o.error_codigo} for o in operations]
    result['recursos']=[{'id':str(r.id),'rol':r.rol,'preparado':bool(r.acceso_metadata.get('local_health')),'ausencia_confirmada':bool(r.ausencia_confirmada_at)} for r in resources]
    return JSONResponse(result,headers={'Cache-Control':'no-store'})


@router.get('/{identity}/eventos')
async def eventos(identity:UUID,limit:int=Query(default=20,ge=1,le=50),cursor:UUID|None=None,actor=Depends(require_admin),db:AsyncSession=Depends(get_db)):
    await ensayo_service.obtener(db,identity,actor=actor)
    query=select(EventoEnsayo).where(EventoEnsayo.ensayo_id==identity)
    if cursor:
        previous=await db.get(EventoEnsayo,cursor)
        if not previous or previous.ensayo_id!=identity:raise error(409,'cursor_desactualizado','Consultá nuevamente los eventos del ensayo')
        query=query.where(or_(EventoEnsayo.creado_at>previous.creado_at,and_(EventoEnsayo.creado_at==previous.creado_at,EventoEnsayo.id>previous.id)))
    rows=list((await db.scalars(query.order_by(EventoEnsayo.creado_at,EventoEnsayo.id).limit(limit+1))).all())
    next_cursor=str(rows[limit-1].id) if len(rows)>limit else None
    rows=rows[:limit]
    return JSONResponse({'next_cursor':next_cursor,'items':[{'id':str(r.id),'anterior':r.anterior,'nuevo':r.nuevo,'actor_tipo':r.actor_tipo,'motivo':r.motivo,'creado_at':r.creado_at.isoformat()} for r in rows]},headers={'Cache-Control':'no-store'})


@router.post('/{identity}/confirmar-entradas')
async def confirmar(identity:UUID,body:ConfirmarEntradas,clave:str=Header(alias='Idempotency-Key'),actor=Depends(require_admin),db:AsyncSession=Depends(get_db)):
    return await responder(db,ensayo_service.accion(db,identity,actor=actor,data=body,clave=clave,action='confirmar-entradas'))


@router.post('/{identity}/comprobar')
async def comprobar(identity:UUID,body:ComprobarEnsayo,clave:str=Header(alias='Idempotency-Key'),actor=Depends(require_admin),db:AsyncSession=Depends(get_db)):
    return await responder(db,ensayo_service.comprobar(db,identity,actor=actor,data=body,clave=clave))


@router.post('/{identity}/descartar')
async def descartar(identity:UUID,body:DescartarEnsayo,clave:str=Header(alias='Idempotency-Key'),actor=Depends(require_admin),db:AsyncSession=Depends(get_db)):
    return await responder(db,ensayo_service.accion(db,identity,actor=actor,data=body,clave=clave,action='descartar'))


@router.post('/{identity}/reintentar')
async def reintentar(identity:UUID,body:RevisionEsperada,clave:str=Header(alias='Idempotency-Key'),actor=Depends(require_admin),db:AsyncSession=Depends(get_db)):
    return await responder(db,ensayo_service.accion(db,identity,actor=actor,data=body,clave=clave,action='reintentar'))


@router.post('/{identity}/reintentar-limpieza')
async def limpiar(identity:UUID,body:RevisionEsperada,clave:str=Header(alias='Idempotency-Key'),actor=Depends(require_admin),db:AsyncSession=Depends(get_db)):
    return await responder(db,ensayo_service.accion(db,identity,actor=actor,data=body,clave=clave,action='reintentar-limpieza'))


@router.post('/{identity}/recursos/{recurso_id}/revelar-acceso')
async def revelar(identity:UUID,recurso_id:UUID,actor=Depends(require_admin),db:AsyncSession=Depends(get_db)):
    row=await ensayo_service.obtener(db,identity,actor=actor)
    resource=await db.get(RecursoEnsayo,recurso_id)
    if not resource or resource.ensayo_id!=row.id:raise error(404,'recurso_no_encontrado','Recurso de ensayo no encontrado')
    if row.cancelada_at or (row.expires_at and db_utc(row.expires_at)<=clock.now()) or resource.ausencia_confirmada_at or not resource.credenciales_encrypted or not resource.acceso_metadata.get('local_health'):
        raise error(409,'acceso_no_disponible','El recurso no tiene acceso confirmado')
    values=configured_keyring().decrypt(resource.credenciales_encrypted,context=f'ensayo:{resource.id}:secretos')
    db.add(EventoSeguridad(actor_usuario_id=actor.id,accion='revelar_acceso_ensayo',resultado='completado',referencia=str(resource.id)))
    await db.commit()
    return JSONResponse({'acceso':resource.acceso_metadata,'credenciales':values},headers={'Cache-Control':'no-store'})
