"""Canonical, sanitized console ingestion. Database commit precedes node ACK.

Helpers with a db argument never commit: a portal milestone and its operation
phase belong to the caller's same transaction. Network I/O is outside that scope.
"""
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select,func

from app.models.consola_operacion import ConsolaOperacion,ConsolaFragmento
from app.models.identidad_infraestructura import IdentidadInfraestructura
from app.models.intento_despliegue import IntentoDespliegue
from app.models.operacion_infraestructura import OperacionInfraestructura
from app.services.operacion_service import condicion_lease
from app.utils.clock import clock
from app.utils.errors import error
from infra.applications.job.protocol import JobError,canonical,parse_request,parse_response,PHASES

MAX_BYTES=10000000
RETENTION_DAYS=30
EVENTS={
    'preparando':('preparacion','Preparando el despliegue.'),
    'creando_recurso':('creacion','Creando el recurso de la aplicación.'),
    'recurso_creado':('creacion','Recurso creado.'),
    'recurso_para_instalar':('entorno','Recurso listo para instalar la aplicación.'),
    'esperando_instalacion':('entorno','Esperando turno para instalar la aplicación.'),
    'entorno_listo':('entorno','Entorno preparado.'),
    'instalacion_solicitada':('instalacion','Instalación solicitada al nodo.'),
    'comprobando':('comprobacion','Comprobando el funcionamiento de la aplicación.'),
    'disponible':('finalizada','La aplicación está disponible.'),
    'fallo':('finalizada','No se pudo completar el despliegue.'),
    'sin_confirmacion':('finalizada','No se pudo confirmar el resultado del despliegue.'),
}
FINAL={'disponible','fallo','sin_confirmacion'}


def _conflict():
    return error(409,'consola_no_confirmada','No se pudo confirmar la información de este despliegue')


async def _locked(db,lease):
    operation=await db.scalar(select(OperacionInfraestructura).where(*condicion_lease(lease))
        .with_for_update().execution_options(populate_existing=True))
    if operation is None:raise _conflict()
    attempt=await db.scalar(select(IntentoDespliegue).where(IntentoDespliegue.operacion_id==operation.id)
        .with_for_update().execution_options(populate_existing=True))
    root=operation.operacion_raiz_id or operation.id
    if attempt is None or attempt.operacion_raiz_id!=root:raise _conflict()
    if root!=operation.id:
        parent=await db.scalar(select(OperacionInfraestructura).where(OperacionInfraestructura.id==root).with_for_update())
        if parent is None:raise _conflict()
    header=await db.scalar(select(ConsolaOperacion).where(ConsolaOperacion.operacion_raiz_id==root)
        .with_for_update().execution_options(populate_existing=True))
    if header is None:
        header=ConsolaOperacion(operacion_raiz_id=root);db.add(header);await db.flush()
    return operation,attempt,header


def _text(value):
    try:
        if (type(value) is not str or not 1<=len(value.encode('utf-8'))<=8192
                or any(ord(c)<32 and c not in '\n\t' or 127<=ord(c)<=159
                    or '\u202a'<=c<='\u202e' or '\u2066'<=c<='\u2069' for c in value)):raise ValueError()
        return len(value.encode('utf-8'))
    except (ValueError,UnicodeError):raise _conflict() from None


async def _append(db,header,attempt,*,source,key,source_seq,fase,stream,text,captured_at):
    size=_text(text)
    if fase not in PHASES or stream not in {'sistema','stdout','stderr'}:raise _conflict()
    row=ConsolaFragmento(operacion_raiz_id=header.operacion_raiz_id,seq=header.next_seq,
        intento_id=attempt.id,execution_id=attempt.execution_id,source=source,source_key=key,
        source_seq=source_seq,captured_at=captured_at,ingested_at=clock.now(),fase=fase,
        stream=stream,texto_depurado=text,utf8_bytes=size)
    db.add(row)
    header.last_seq=header.next_seq;header.next_seq+=1;header.retained_bytes+=size
    header.last_captured_at=captured_at;header.last_ingested_at=clock.now()
    header.expired=False
    await db.flush()


async def _trim(db,header):
    cutoff=clock.now()-timedelta(days=RETENTION_DAYS)
    # Bounded batches avoid loading a whole retained console into Python.
    for expired in (True,False):
        while True:
            if not expired and header.retained_bytes<=MAX_BYTES:break
            query=select(ConsolaFragmento).where(ConsolaFragmento.operacion_raiz_id==header.operacion_raiz_id)
            if expired:query=query.where(ConsolaFragmento.captured_at<cutoff)
            rows=list((await db.scalars(query.order_by(ConsolaFragmento.seq).limit(1000))).all())
            if not rows:break
            for row in rows:
                if not expired and header.retained_bytes<=MAX_BYTES:break
                header.retained_bytes-=row.utf8_bytes
                header.dropped_bytes+=row.utf8_bytes;header.dropped_messages+=1;header.truncated=True
                if expired:header.expired=True
                await db.delete(row)
            await db.flush()
    first=await db.scalar(select(func.min(ConsolaFragmento.seq)).where(
        ConsolaFragmento.operacion_raiz_id==header.operacion_raiz_id))
    header.first_retained_seq=first if first is not None else header.next_seq


async def emitir_hito(db,lease,*,hito):
    if type(hito) is not str or hito not in EVENTS:raise _conflict()
    operation,attempt,header=await _locked(db,lease)
    phase,text=EVENTS[hito]
    key=f'hito:{attempt.id}:{phase}:{hito}'
    context=dict(operation.contexto_seguro)
    seen=list(context.get('consola_hitos',[]))
    if key in seen:return False  # Tombstone survives text quota/expiry.
    if len(seen)>=len(EVENTS):raise _conflict()
    if hito=='disponible' and attempt.runner_job_id is None:raise _conflict()
    if hito in FINAL and attempt.runner_job_id is not None:
        final=context.get('consola_job_final')
        if (type(final) is not dict or attempt.ultimo_source_seq<final.get('last_source_seq',2**63)):
            raise _conflict()
        if hito=='disponible':
            result=final.get('resultado') or {}
            checks=set(result.get('comprobaciones',[]))
            if (final.get('estado')!='confirmado' or result.get('recurso_configurado') is not True
                    or not {'aislamiento','runtime','salud'}<=checks
                    or not checks & {'acceso_web','autenticacion_tcp'}):raise _conflict()
        elif hito=='fallo' and final.get('estado')!='fallido':raise _conflict()
    if any(key.endswith(':'+last) for key in seen for last in FINAL):raise _conflict()
    phases=('preparacion','creacion','entorno','instalacion','configuracion','arranque','comprobacion','finalizada')
    if operation.fase in phases and phases.index(phase)<phases.index(operation.fase):raise _conflict()
    await _append(db,header,attempt,source='portal',key=key,source_seq=None,
        fase=phase,stream='sistema',text=text,captured_at=clock.now())
    operation.fase=phase;operation.updated_at=clock.now()
    context['consola_hitos']=[*seen,key];operation.contexto_seguro=context
    if hito in FINAL:header.ultimo_resultado_seguro={'hito':hito,'texto':text}
    await _trim(db,header);await db.flush()
    return True


async def ingerir(db,lease,*,request,response):
    """Caller commits before using through_seq to request node ACK."""
    try:
        request=parse_request(canonical(request))
        if request['action']!='read':raise ValueError()
        response=parse_response(canonical(response),request=request)
        if response['ok'] is not True:raise ValueError()
        data=response['data']
    except (JobError,ValueError,TypeError,KeyError,UnicodeError,RecursionError):raise _conflict() from None
    operation,attempt,header=await _locked(db,lease)
    identity=await db.get(IdentidadInfraestructura,attempt.identidad_infraestructura_id)
    if (identity is None or operation.identidad_infraestructura_id!=identity.id
            or request['operation_id']!=str(operation.id) or request['operacion_raiz_id']!=str(header.operacion_raiz_id)
            or request['intento_id']!=str(attempt.id) or request['execution_id']!=str(attempt.execution_id)
            or request['lease_generation']!=lease.generation or request['cluster_uuid']!=identity.cluster_id
            or request['node']!=identity.nodo or request['vmid']!=identity.vmid
            or request['pool']!=identity.pool_catedra or request['resource_uuid']!=str(identity.resource_uuid)
            or request['configuracion_sha256']!=attempt.configuracion_sha256
            or data['fingerprint']!=operation.contexto_seguro.get('job_fingerprint')
            or data['acknowledged_seq']>attempt.ultimo_source_seq):raise _conflict()
    if attempt.node_boot_id is not None and str(attempt.node_boot_id)!=data['node_boot_id']:raise _conflict()
    cursor=attempt.ultimo_source_seq
    # Build and validate the complete prefix before any fragment/cursor changes.
    pending=[(item['source_seq'],item['source_seq'],'item',item) for item in data['items'] if item['source_seq']>cursor]
    pending += [(max(cursor+1,r['from_seq']),r['through_seq'],'loss',r) for r in data['dropped_ranges'] if r['through_seq']>cursor]
    pending.sort(key=lambda item:item[0])
    end=cursor
    for start,through,kind,item in pending:
        if start!=end+1:raise _conflict()
        if kind=='item':_text(item['texto_depurado'])
        end=through
    if end>data['last_source_seq']:raise _conflict()
    context=dict(operation.contexto_seguro)
    prior=context.get('consola_job_final')
    if prior and prior['estado'] in {'confirmado','fallido'}:
        if prior!={'estado':data['estado'],'last_source_seq':data['last_source_seq'],'resultado':data['resultado']}:
            raise _conflict()
    if pending and any(key.endswith(':'+last) for key in context.get('consola_hitos',[]) for last in FINAL):
        raise _conflict()
    for start,through,kind,item in pending:
        if kind=='loss':
            count=through-start+1
            await _append(db,header,attempt,source='portal',key=f'perdida:{start}:{through}',source_seq=None,
                fase=data['fase'],stream='sistema',text=f'El nodo omitió {count} mensajes de consola.',captured_at=clock.now())
            header.dropped_messages+=count;header.truncated=True
            # Never invent bytes for a partially overlapping original loss range.
            if start==item['from_seq']:header.dropped_bytes+=item['bytes']
        else:
            await _append(db,header,attempt,source='runner',key=str(start),source_seq=start,
                fase=item['fase'],stream=item['stream'],text=item['texto_depurado'],
                captured_at=datetime.fromisoformat(item['captured_at'].replace('Z','+00:00')))
    attempt.ultimo_source_seq=end
    # A successful empty batch proves the reader is alive, without inventing
    # a new fragment or moving the producer's capture timestamp.
    header.last_ingested_at=clock.now()
    attempt.node_boot_id=UUID(data['node_boot_id']);attempt.runner_job_id=str(attempt.execution_id)
    if data['estado'] in {'confirmado','fallido','incierto'}:
        operation.contexto_seguro={**operation.contexto_seguro,'consola_job_final':{
            'estado':data['estado'],'last_source_seq':data['last_source_seq'],'resultado':data['resultado']}}
    elif 'consola_job_final' in context:
        context.pop('consola_job_final');operation.contexto_seguro=context
    await _trim(db,header);await db.flush()
    return {'through_seq':end,'inserted':len(pending)}


async def ingerir_y_confirmar(sessions,lease,*,request,response,client):
    try:
        request=parse_request(canonical(request))
        response=parse_response(canonical(response),request=request)
    except (JobError,ValueError,TypeError,KeyError,UnicodeError,RecursionError):raise _conflict() from None
    async with sessions() as db,db.begin():
        result=await ingerir(db,lease,request=request,response=response)
    # No SQL transaction or row lock remains during SSH. A failed ACK is safe to
    # replay after committing the same batch again, without duplicated fragments.
    ack={k:v for k,v in request.items() if k not in {'after','limit_bytes'}}
    ack.update(action='ack',through_seq=result['through_seq'])
    confirmed=False
    try:
        reply=await client.execute(ack,expected_fingerprint=response['data']['fingerprint'])
        confirmed=reply['ok'] is True
    except (JobError,TimeoutError,OSError):pass
    return {**result,'ack_confirmed':confirmed}


async def purgar(db,root_id):
    header=await db.scalar(select(ConsolaOperacion).where(ConsolaOperacion.operacion_raiz_id==root_id)
        .with_for_update().execution_options(populate_existing=True))
    if header is not None:await _trim(db,header);await db.flush()


async def consultar(
    db,
    operation_id: UUID,
    *,
    usuario,
    after: int | None = None,
    before: int | None = None,
    limit_bytes: int = 65536,
    through_seq: int | None = None,
):
    if getattr(usuario, 'rol', None) != 'admin':
        raise error(403, 'acceso_denegado', 'Acceso denegado')

    if after is not None and before is not None:
        raise error(422, 'parametros_consulta_invalidos', 'Los parámetros after y before son mutuamente excluyentes')
    if after is not None and after < 0:
        raise error(422, 'parametros_consulta_invalidos', 'El parámetro after debe ser mayor o igual a 0')
    if before is not None and before <= 0:
        raise error(422, 'parametros_consulta_invalidos', 'El parámetro before debe ser mayor a 0')
    if limit_bytes < 1 or limit_bytes > 65536:
        raise error(422, 'limite_invalido', 'El límite de bytes debe estar entre 1 y 65536')
    if through_seq is not None and through_seq <= 0:
        raise error(422, 'parametros_consulta_invalidos', 'El parámetro through_seq debe ser mayor a 0')

    operation = await db.get(OperacionInfraestructura, operation_id)
    if operation is None:
        raise error(404, 'operacion_no_encontrada', 'Operación no encontrada')
    from app.services.operacion_service import anexar_progreso_aplicacion
    await anexar_progreso_aplicacion(db, [operation])

    root_id = operation.operacion_raiz_id or operation.id
    header = await db.get(ConsolaOperacion, root_id)

    latest_attempt = await db.scalar(
        select(IntentoDespliegue)
        .where(IntentoDespliegue.operacion_raiz_id == root_id)
        .order_by(IntentoDespliegue.numero.desc())
        .limit(1)
    )
    intento_efectivo = latest_attempt.numero if latest_attempt is not None else 1

    if header is None:
        return {
            'operation_id': operation.id,
            'operacion_raiz_id': root_id,
            'estado': operation.estado,
            'fase': getattr(operation, '_fase_aplicacion', None) or operation.fase,
            'intento_efectivo': intento_efectivo,
            'items': [],
            'next_cursor': None,
            'previous_cursor': None,
            'has_more': False,
            'first_retained_seq': 1,
            'last_seq': 0,
            'truncated': False,
            'expired': False,
            'dropped_messages': 0,
            'last_captured_at': None,
            'last_ingested_at': None,
            'resultado_final': None,
        }

    base_query = (
        select(ConsolaFragmento, IntentoDespliegue.numero)
        .outerjoin(IntentoDespliegue, ConsolaFragmento.intento_id == IntentoDespliegue.id)
        .where(ConsolaFragmento.operacion_raiz_id == root_id)
    )
    if through_seq is not None:
        base_query = base_query.where(ConsolaFragmento.seq <= through_seq)

    items = []
    has_more = False
    truncated = header.truncated

    if after is not None:
        if after < header.first_retained_seq:
            truncated = True
            query = base_query.where(ConsolaFragmento.seq >= header.first_retained_seq).order_by(ConsolaFragmento.seq.asc())
        else:
            query = base_query.where(ConsolaFragmento.seq > after).order_by(ConsolaFragmento.seq.asc())

        total_bytes = 0
        rows = list((await db.execute(query)).all())
        for frag, intento_num in rows:
            if total_bytes + frag.utf8_bytes > limit_bytes and items:
                has_more = True
                break
            items.append({
                'seq': frag.seq,
                'intento': intento_num or 1,
                'captured_at': frag.captured_at,
                'fase': frag.fase,
                'stream': frag.stream,
                'texto_depurado': frag.texto_depurado,
            })
            total_bytes += frag.utf8_bytes
        if not has_more and len(rows) > len(items):
            has_more = True

    elif before is not None:
        query = base_query.where(ConsolaFragmento.seq < before).order_by(ConsolaFragmento.seq.desc())
        total_bytes = 0
        rows = list((await db.execute(query)).all())
        collected = []
        for frag, intento_num in rows:
            if total_bytes + frag.utf8_bytes > limit_bytes and collected:
                has_more = True
                break
            collected.append({
                'seq': frag.seq,
                'intento': intento_num or 1,
                'captured_at': frag.captured_at,
                'fase': frag.fase,
                'stream': frag.stream,
                'texto_depurado': frag.texto_depurado,
            })
            total_bytes += frag.utf8_bytes
        if not has_more and len(rows) > len(collected):
            has_more = True
        items = list(reversed(collected))

    else:
        query = base_query.order_by(ConsolaFragmento.seq.desc())
        total_bytes = 0
        rows = list((await db.execute(query)).all())
        collected = []
        for frag, intento_num in rows:
            if total_bytes + frag.utf8_bytes > limit_bytes and collected:
                has_more = True
                break
            collected.append({
                'seq': frag.seq,
                'intento': intento_num or 1,
                'captured_at': frag.captured_at,
                'fase': frag.fase,
                'stream': frag.stream,
                'texto_depurado': frag.texto_depurado,
            })
            total_bytes += frag.utf8_bytes
        if not has_more and len(rows) > len(collected):
            has_more = True
        items = list(reversed(collected))

    next_cursor = items[-1]['seq'] if items else (after if after is not None else None)
    previous_cursor = items[0]['seq'] if items else None

    return {
        'operation_id': operation.id,
        'operacion_raiz_id': root_id,
        'estado': operation.estado,
        'fase': getattr(operation, '_fase_aplicacion', None) or operation.fase,
        'intento_efectivo': intento_efectivo,
        'items': items,
        'next_cursor': next_cursor,
        'previous_cursor': previous_cursor,
        'has_more': has_more,
        'first_retained_seq': header.first_retained_seq,
        'last_seq': header.last_seq,
        'truncated': truncated,
        'expired': header.expired,
        'dropped_messages': header.dropped_messages,
        'last_captured_at': header.last_captured_at,
        'last_ingested_at': header.last_ingested_at,
        'resultado_final': header.ultimo_resultado_seguro,
    }

