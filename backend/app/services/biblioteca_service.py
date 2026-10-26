"""Búsqueda e incorporación sin acceso a APIs de infraestructura."""
import base64
from copy import deepcopy
import hashlib
import json
from uuid import UUID
from sqlalchemy import select,text
from app.models.incorporacion_aplicacion import IncorporacionAplicacion
from app.models.evento_seguridad import EventoSeguridad
from app.services.acceso_service import requiere_admin_actual
from app.services.community_scripts_client import get_fuente
from app.services.idempotencia_service import ejecutar, ResultadoDecision
from app.utils.errors import error


def present(row):
    value={key:deepcopy(getattr(row,key)) for key in ['proveedor','identidad_externa','revision_fuente','version_externa',
        'nombre','descripcion','categorias','aliases','comando_origen','url_origen','comando_sha256','revision','datos_origen']}
    value.update(id=str(row.id),created_at=row.created_at.isoformat(),
        faltantes=[key for key in ['descripcion','version_externa'] if not getattr(row,key)],
        compatibilidad=row.datos_origen.get('compatibilidad','sin_comprobar'))
    return value


def paginate(items, *, query, limit, cursor, revision):
    fingerprint=hashlib.sha256(json.dumps([query,revision],sort_keys=True).encode()).hexdigest()
    offset=0
    if cursor:
        try:
            value=json.loads(base64.urlsafe_b64decode(cursor.encode()))
            if set(value)!={'offset','fingerprint'} or value['fingerprint']!=fingerprint or type(value['offset']) is not int or value['offset']<0:raise ValueError()
            offset=value['offset']
        except (ValueError,TypeError,KeyError,UnicodeError):
            raise error(409,'cursor_desactualizado','La búsqueda cambió; volvé a consultar') from None
    after=offset+limit
    next_cursor=base64.urlsafe_b64encode(json.dumps({'offset':after,'fingerprint':fingerprint}).encode()).decode() if after<len(items) else None
    return {'items':items[offset:after],'next_cursor':next_cursor}


async def buscar(db, *, actor, filters):
    await requiere_admin_actual(db,actor)
    items,info=await get_fuente().index()
    q=(filters.q or '').casefold();cat=(filters.categoria or '').casefold()
    items=[item for item in items if (not q or q in ' '.join([item['nombre'],*(item.get('aliases') or [])]).casefold())
        and (not cat or cat in [c.casefold() for c in item['categorias']])]
    return {**paginate(items,query=[q,cat],limit=filters.limit,cursor=filters.cursor,revision=info['revision']), 'fuente':info}


async def incorporar(db, *, actor, data, clave):
    actor=await requiere_admin_actual(db,actor)
    # Fuente sólo dentro de la decisión: replay puede funcionar aun con proveedor caído.
    async def decide(session):
        items,_=await get_fuente().index()
        source=next((item for item in items if item['identidad_externa']==data.identidad_externa and item['revision_fuente']==data.revision_fuente),None)
        if source is None:raise error(409,'fuente_desactualizada','La ficha cambió; repetí la búsqueda')
        origin=source.get('version_externa') or 'desconocida:'+source['revision_fuente']
        if session.bind.dialect.name=='postgresql':
            lock=int.from_bytes(hashlib.sha256(f'incorporar:{data.identidad_externa}:{origin}'.encode()).digest()[:8],signed=True)
            await session.execute(text('SELECT pg_advisory_xact_lock(:lock)'),{'lock':lock})
        row=await session.scalar(select(IncorporacionAplicacion).where(IncorporacionAplicacion.proveedor=='community-scripts',
            IncorporacionAplicacion.identidad_externa==data.identidad_externa,IncorporacionAplicacion.origen_clave==origin))
        if row:return ResultadoDecision(200,present(row))
        fields=['identidad_externa','revision_fuente','comando_sha256','comando_origen','url_origen','version_externa','nombre','descripcion','categorias','aliases']
        row=IncorporacionAplicacion(**{key:deepcopy(source.get(key)) for key in fields},origen_clave=origin,datos_origen=deepcopy(source),creado_por=actor.id)
        session.add(row);await session.flush()
        session.add(EventoSeguridad(actor_usuario_id=actor.id,accion='incorporar_aplicacion',resultado='completado',referencia=str(row.id)))
        return ResultadoDecision(201,present(row))
    return await ejecutar(db,actor_id=actor.id,clave=clave,metodo='POST',ruta='/biblioteca/incorporaciones',payload=data.model_dump(),decidir=decide)


async def obtener(db,identity,*,actor,bloquear=False):
    await requiere_admin_actual(db,actor)
    query=select(IncorporacionAplicacion).where(IncorporacionAplicacion.id==identity).execution_options(populate_existing=True)
    if bloquear:query=query.with_for_update()
    row=await db.scalar(query)
    if not row:raise error(404,'incorporacion_no_encontrada','Incorporación no encontrada')
    return row


async def listar(db,*,actor,filters):
    await requiere_admin_actual(db,actor)
    rows=list((await db.scalars(select(IncorporacionAplicacion).order_by(IncorporacionAplicacion.created_at,IncorporacionAplicacion.id))).all())
    # Revisión de lista incluye contenido/orden, para no avanzar con cursor de otro snapshot.
    revision=hashlib.sha256(str([(str(r.id),r.revision) for r in rows]).encode()).hexdigest()
    return paginate([present(r) for r in rows],query='incorporaciones',limit=filters.limit,cursor=filters.cursor,revision=revision)


async def editar(db,identity,*,actor,data,clave):
    actor=await requiere_admin_actual(db,actor)
    async def decide(session):
        row=await obtener(session,identity,actor=actor,bloquear=True)
        if row.revision!=data.revision_esperada:raise error(409,'revision_desactualizada','La ficha cambió; revisá los datos',revision=row.revision)
        for key,value in data.model_dump(exclude_unset=True).items():
            if key=='revision_esperada':continue
            if key=='nombre' and (value is None or not value.strip()):raise error(422,'datos_invalidos','Indicá un nombre válido')
            if key in {'aliases','categorias'} and value is None:value=[]
            setattr(row,key,value)
        row.revision+=1;await session.flush()
        session.add(EventoSeguridad(actor_usuario_id=actor.id,accion='editar_incorporacion',resultado='completado',referencia=str(row.id)))
        return ResultadoDecision(200,present(row))
    return await ejecutar(db,actor_id=actor.id,clave=clave,metodo='PATCH',ruta=f'/biblioteca/incorporaciones/{identity}',payload=data.model_dump(exclude_unset=True),decidir=decide)
