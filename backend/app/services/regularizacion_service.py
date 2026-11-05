"""Decisión administrativa explícita sobre legado, respaldada por propiedad actual."""
from copy import deepcopy
from uuid import uuid4

from sqlalchemy import select,or_

from app.config import get_settings
from app.models.bitacora_cierre import BitacoraCierre
from app.models.compromiso_capacidad import CompromisoCapacidad
from app.models.identidad_infraestructura import IdentidadInfraestructura
from app.models.operacion_infraestructura import OperacionInfraestructura
from app.models.pedido import Pedido,PedidoHistorial
from app.models.servicio import Servicio,EstadoServicio
from app.models.vigencia import VigenciaAutorizada
from app.services import capacidad_service,inventario_service,identidad_infra_service,historial_service
from app.services.acceso_service import requiere_admin_actual
from app.services.backfill_cierre_service import _state,_hash,_json
from app.services.idempotencia_service import ejecutar,ResultadoDecision
from app.services.vigencia_service import resolver_fechas,periodos_vigentes,resumir_cobertura
from app.utils.clock import clock,db_utc
from app.utils.errors import error
from app.services.legado_cierre import cargar,valor as legado

OPEN={'pendiente','en_curso','incierta'}
GIB=1024**3


def _vmid(value):
    return int(value) if isinstance(value,str) and value.isascii() and value.isdecimal() and int(value)>0 else None


async def _view(db,identity,*,lock=False):
    query=select(Servicio).where(Servicio.id==identity).execution_options(populate_existing=True)
    if lock: query=query.with_for_update().execution_options(populate_existing=True)
    row=await db.scalar(query)
    if row is None or row.deleted_at: raise error(404,'servicio_no_encontrado','Servicio no encontrado')
    request_query=select(Pedido).where(Pedido.id==row.pedido_id).execution_options(populate_existing=True)
    if lock: request_query=request_query.with_for_update()
    request=await db.scalar(request_query) if row.pedido_id else None
    ledger_query=select(CompromisoCapacidad).where(CompromisoCapacidad.servicio_id==row.id,CompromisoCapacidad.liberado_at.is_(None))
    if lock: ledger_query=ledger_query.with_for_update().execution_options(populate_existing=True)
    ledger=await db.scalar(ledger_query)
    owner_query=select(IdentidadInfraestructura).where(IdentidadInfraestructura.id==row.identidad_infraestructura_id).execution_options(populate_existing=True)
    if lock: owner_query=owner_query.with_for_update()
    owner=await db.scalar(owner_query) if row.identidad_infraestructura_id else None
    periods_query=select(VigenciaAutorizada).where(VigenciaAutorizada.servicio_id==row.id).execution_options(populate_existing=True)
    if lock: periods_query=periods_query.with_for_update()
    periods=list((await db.scalars(periods_query)).all())
    await cargar(db,'servicios',[row])
    if request: await cargar(db,'pedidos',[request])
    state=_json(_state('servicio',row,request=request,ledger=ledger,identity=owner,periods=periods))
    return {'row':row,'request':request,'ledger':ledger,'owner':owner,'periods':periods,'state':state,'source':_hash(state)}


async def _open(db,view):
    row,owner=view['row'],view['owner']
    clauses=[OperacionInfraestructura.servicio_id==row.id]
    if row.pedido_id: clauses.append(OperacionInfraestructura.pedido_id==row.pedido_id)
    if owner: clauses.append(OperacionInfraestructura.identidad_infraestructura_id==owner.id)
    return await db.scalar(select(OperacionInfraestructura.id).where(or_(*clauses),OperacionInfraestructura.estado.in_(OPEN)).limit(1))


async def _observed(view,*,pve=None):
    row,owner=view['row'],view['owner']
    if (not owner or owner.servicio_id!=row.id or owner.ausencia_confirmada_at
        or owner.pool_catedra!=f'catedra-{row.catedra_id}' or owner.nodo!=row.proxmox_node
        or owner.vmid!=_vmid(row.proxmox_vmid)):
        return None
    try:
        inventory=await inventario_service.leer(pve)
        resource=inventory['recursos'].get(owner.vmid)
        if not resource or not capacidad_service._owned(resource,owner,inventory['cluster_id']): return None
        observation=await identidad_infra_service.observar(owner,pve=pve)
        config=observation.config
        if (observation.estado!='propia' or observation.status not in {'running','stopped'} or observation.status!=resource['estado']
            or config.get('unprivileged') not in [1,True,'1'] or len(resource['volumenes'])!=1): return None
        volume,size=next(iter(resource['volumenes'].items()))
        scope,suffix=volume
        destinations=[(node,storage) for (node,storage),path in inventory['destinos'].items() if node==owner.nodo and path==scope]
        if len(destinations)!=1 or size%GIB or size<=0: return None
        node,storage=destinations[0]
        root=config['rootfs'].split(',')
        declared=next(part.split('=',1)[1] for part in root if part.startswith('size='))
        if (root[0].removeprefix('volume=')!=f'{storage}:{suffix}' or inventario_service.disk_size(declared)!=size
            or inventario_service.integer(config['cores'],minimum=1)!=resource['configurado_vcpus']
            or inventario_service.integer(config['memory'],minimum=1)!=resource['configurado_ram_mb']): return None
        return {'asignacion':{'vcpus':resource['configurado_vcpus'],'ram_mb':resource['configurado_ram_mb'],'disk_gb':size//GIB},
            'estado':observation.status,'nodo':node,'storage':storage,'scope':scope,
            'marca_sha256':_hash(resource['marca'])}
    except Exception:
        return None


async def _context(db,service_id,*,canonical_id=None,pve=None):
    view=await _view(db,service_id)
    row,request,ledger=view['row'],view['request'],view['ledger']
    reasons=[]
    if row.tipo!='lxc': reasons.append('El recurso histórico no es LXC; conserva consulta sin nuevas activaciones')
    legacy=not row.definicion_version_id and not (request and request.definicion_version_id)
    if not legacy:
        reasons.append('La versión publicada tiene su propio flujo de asignación y vigencia')
    if legado(row,'credenciales_acceso') is not None: reasons.append('Completar primero la migración cifrada del legado')
    if await _open(db,view): reasons.append('Reconciliar la operación abierta antes de regularizar')
    candidates=list((await db.scalars(select(Servicio).where(Servicio.deleted_at.is_(None),Servicio.id!=row.id))).all())
    duplicates=[r for r in candidates if _vmid(row.proxmox_vmid) is not None and _vmid(r.proxmox_vmid)==_vmid(row.proxmox_vmid)]
    if duplicates: reasons.append('Hay registros duplicados del recurso; resolver el registro principal')
    if not request or request.catedra_id!=row.catedra_id: reasons.append('Recuperar la relación comprobada con el pedido histórico')
    if ledger and (ledger.pedido_id!=row.pedido_id or ledger.identidad_infraestructura_id not in {None,row.identidad_infraestructura_id}):
        reasons.append('Reconciliar la relación del compromiso con el pedido y la identidad')
    if request:
        clauses=[CompromisoCapacidad.pedido_id==request.id]
        if view['owner']: clauses.append(CompromisoCapacidad.identidad_infraestructura_id==view['owner'].id)
        conflict=await db.scalar(select(CompromisoCapacidad.id).where(CompromisoCapacidad.liberado_at.is_(None),
            or_(*clauses),or_(CompromisoCapacidad.servicio_id!=row.id,CompromisoCapacidad.servicio_id.is_(None))).limit(1))
        if conflict: reasons.append('Existe otro compromiso abierto para el pedido o la identidad; reconciliar primero')
    observation=await _observed(view,pve=pve) if row.tipo=='lxc' else None
    if observation is None: reasons.append('Falta comprobar la propiedad y configuración del recurso; requiere revisión institucional')
    periods=await periodos_vigentes(db,row.id)
    if (row.asignacion_snapshot and row.nombre_snapshot and row.modelo_servicio and ledger
        and ledger.estado=='materializado' and view['owner'] and view['owner'].estado=='materializada' and periods):
        reasons.append('El registro ya está regularizado; usar los flujos de vigencia y acceso')
    period=periods[0] if len(periods)==1 else None
    canonical_view=None;can_archive=False
    if canonical_id and canonical_id!=row.id:
        canonical_view=await _view(db,canonical_id)
        primary=canonical_view['row']
        primary_observed=await _observed(canonical_view,pve=pve)
        can_archive=bool(legacy and row.tipo=='lxc' and primary.tipo=='lxc' and primary_observed and primary.catedra_id==row.catedra_id
            and _vmid(primary.proxmox_vmid)==_vmid(row.proxmox_vmid)
            and primary.proxmox_node==row.proxmox_node and not view['owner'] and not ledger
            and legado(row,'credenciales_acceso') is None and not await _open(db,view) and not await _open(db,canonical_view))
    source=_hash({'registro':view['source'],'principal':canonical_view['source'] if canonical_view else None,
        'observacion':observation,'principal_observado':primary_observed if canonical_view else None})
    preview={'servicio_id':row.id,'fuente_sha256':source,'puede_regularizar':not reasons,
        'puede_archivar_duplicado':can_archive,'motivos':reasons,
        'nombre':row.nombre_snapshot or f'Servicio histórico #{row.id}',
        'modelo_servicio':row.modelo_servicio or (request.modelo_servicio.value if request else None),
        'asignacion_observada':observation['asignacion'] if observation else None,
        'estado_observado':observation['estado'] if observation else None,
        'desde':period.desde_local.isoformat() if period else None,'hasta':period.hasta_local.isoformat() if period else None,
        'zona_horaria':period.zona_horaria if period else get_settings().institutional_timezone,
        'conflictos':[{'id':r.id,'nombre':r.nombre_snapshot or f'Servicio #{r.id}',
            'misma_catedra':r.catedra_id==row.catedra_id,'con_identidad':bool(r.identidad_infraestructura_id)} for r in duplicates]}
    return view,preview,observation,canonical_view


async def evaluar(db,service_id,*,actor,canonical_id=None,pve=None):
    await requiere_admin_actual(db,actor)
    _,preview,_,_=await _context(db,service_id,canonical_id=canonical_id,pve=pve)
    return preview


async def confirmar(db,service_id,*,actor,body,clave,pve=None):
    actor=await requiere_admin_actual(db,actor)
    payload=body.model_dump(mode='json')
    async def decide(session):
        await requiere_admin_actual(session,actor)
        view,preview,observed,_=await _context(session,service_id,pve=pve)
        if preview['fuente_sha256']!=body.fuente_sha256 or not preview['puede_regularizar']:
            raise error(409,'regularizacion_no_verificable','Los datos o la propiedad requieren una evaluación nueva')
        if body.asignacion.model_dump()!=observed['asignacion']:
            raise error(409,'asignacion_infra_cambiada','Las cantidades deben coincidir con el recurso comprobado')
        try: period=resolver_fechas(body.desde,body.hasta,preview['zona_horaria'])
        except ValueError: raise error(422,'vigencia_invalida','Indicá fechas completas, válidas y ordenadas') from None
        original_periods=await periodos_vigentes(session,service_id)
        if original_periods and not any(p.desde_local==body.desde and p.hasta_local==body.hasta
            and p.zona_horaria==period.zona_horaria for p in original_periods):
            raise error(409,'vigencia_ya_autorizada','Conservar períodos aprobados; modificar mediante el flujo de vigencias')
        async with capacidad_service.bloqueo_capacidad(session):
            locked=await _view(session,service_id,lock=True)
            if locked['source']!=view['source'] or await _open(session,locked):
                raise error(409,'evaluacion_desactualizada','El registro cambió; volvé a evaluar')
            row,request,ledger,owner=locked['row'],locked['request'],locked['ledger'],locked['owner']
            audit_id=uuid4();before=locked['state'];before_power=row.estado.value
            snapshot={'origen':'regularizacion_legacy_admin','template_id':row.template_id,'tipo':'lxc',
                'nombre':body.nombre,'modelo_servicio':body.modelo_servicio,**body.asignacion.model_dump()}
            row.nombre_snapshot=body.nombre;row.modelo_servicio=body.modelo_servicio;row.asignacion_snapshot=snapshot
            row.vcpus_asignados=body.asignacion.vcpus;row.ram_asignada_mb=body.asignacion.ram_mb;row.disk_asignado_gb=body.asignacion.disk_gb
            row.disponibilidad_aplicacion='no_verificada';row.verificado_at=None;row.evidencia_acceso_id=None;row.acceso_red_verificado_at=None
            row.estado=EstadoServicio.RUNNING if observed['estado']=='running' else EstadoServicio.PAUSED if row.estado==EstadoServicio.PAUSED else EstadoServicio.STOPPED
            row.observado_at=clock.now();owner.estado='materializada';owner.ownership_verificada_at=clock.now()
            if ledger is None:
                ledger=CompromisoCapacidad(pedido_id=request.id,servicio_id=row.id,identidad_infraestructura_id=owner.id,
                    nodo=observed['nodo'],storage_id=observed['storage'],storage_scope=observed['scope'])
                session.add(ledger)
            elif ledger.identidad_infraestructura_id not in {None,owner.id}:
                raise error(409,'compromiso_incompatible','Reconciliar el compromiso antes de cambiar su identidad')
            ledger.identidad_infraestructura_id=owner.id;ledger.nodo=observed['nodo'];ledger.storage_id=observed['storage'];ledger.storage_scope=observed['scope']
            ledger.vcpus_retenidos=body.asignacion.vcpus if observed['estado']=='running' else 0
            ledger.ram_mb_retenida=body.asignacion.ram_mb if observed['estado']=='running' else 0
            ledger.disk_bytes_retenidos=body.asignacion.disk_bytes;ledger.estado='materializado';ledger.expira_at=None
            ledger.revision=(ledger.revision or 0)+1
            if not request.asignacion_snapshot: request.asignacion_snapshot=deepcopy(snapshot)
            if not original_periods:
                revision=max([request.revision_decision,*[p.revision_decision for p in locked['periods']]])+1
                request.revision_decision=revision
                entry=VigenciaAutorizada(pedido_id=request.id,revision_decision=revision,servicio_id=row.id,
                    modalidad='personalizado',desde_local=period.desde,hasta_local=period.hasta,zona_horaria=period.zona_horaria,
                    inicio_at=period.inicio_at,fin_exclusivo_at=period.fin_exclusivo_at,aprobado_por=actor.id,
                    aprobado_at=clock.now(),origen='regularizacion_admin')
                session.add(entry)
            row.vence_at=max([period.fin_exclusivo_at,*[db_utc(p.fin_exclusivo_at) for p in original_periods]]).replace(tzinfo=None)
            session.add(historial_service.registrar_servicio(row.id,before_power,row.estado.value,usuario=actor,
                comentario='Regularización explícita: '+body.motivo,evento_clave=f'regularizacion:{audit_id}',
                metadata={'asignacion':snapshot,'catedra_id':row.catedra_id,'referencia':body.referencia,'origen':'regularizacion_legacy'}))
            session.add(PedidoHistorial(pedido_id=request.id,estado_anterior=request.estado.value,estado_nuevo=request.estado.value,
                comentario='Regularización del servicio histórico: '+body.motivo,usuario_id=actor.id,actor_tipo='usuario',
                evento_clave=f'regularizacion:{audit_id}',decision_metadata={'servicio_id':row.id,'referencia':body.referencia}))
            await session.flush()
            after=await _view(session,row.id)
            session.add(BitacoraCierre(id=audit_id,entidad_tipo='servicio',entidad_id=str(row.id),
                fuente_sha256=_hash(before),resultado_sha256=after['source'],accion='regularizar_legacy',
                antes_seguro=before,despues_seguro=after['state'],pendientes=['acceso_no_verificado'],
                actor_usuario_id=actor.id,referencia=body.referencia))
        result={'servicio_id':row.id,'regularizacion_id':str(audit_id),'disponibilidad_aplicacion':'no_verificada'}
        coverage=resumir_cobertura(await periodos_vigentes(session,row.id),clock.now())
        if observed['estado']=='running' and not coverage['cubierto']:
            from app.services.operacion_service import admitir_orden
            pause=await admitir_orden(session,row.id,tipo='pausar',sistema='vencimiento',
                clave='regularizacion-pausa-'+audit_id.hex,motivo='Cobertura actual ausente tras regularización')
            result['operation_id']=pause.resultado.get('operation_id')
        return ResultadoDecision(200,result)
    return await ejecutar(db,actor_id=actor.id,clave=clave,metodo='POST',ruta=f'/servicios/{service_id}/regularizacion',
        payload=payload,decidir=decide,target_tipo='servicio',target_id=service_id)


async def archivar_duplicado(db,service_id,*,actor,body,clave,pve=None):
    actor=await requiere_admin_actual(db,actor)
    async def decide(session):
        await requiere_admin_actual(session,actor)
        view,preview,_,primary=await _context(session,service_id,canonical_id=body.canonico_id,pve=pve)
        if preview['fuente_sha256']!=body.fuente_sha256 or not preview['puede_archivar_duplicado']:
            raise error(409,'duplicado_no_verificable','Conservar registros hasta comprobar principal, pertenencia y compromisos')
        async with capacidad_service.bloqueo_capacidad(session):
            locked={identity:await _view(session,identity,lock=True) for identity in sorted([service_id,body.canonico_id])}
            current=locked[service_id];canonical=locked[body.canonico_id]
            if current['source']!=view['source'] or canonical['source']!=primary['source']:
                raise error(409,'evaluacion_desactualizada','Los registros cambiaron; volvé a evaluar')
            if await _open(session,current) or await _open(session,canonical):
                raise error(409,'operacion_en_curso','Reconciliar operaciones antes de archivar el duplicado')
            row=current['row'];audit_id=uuid4();row.deleted_at=clock.now().replace(tzinfo=None)
            row.disponibilidad_aplicacion='no_verificada'
            session.add(historial_service.registrar_servicio(row.id,row.estado.value,row.estado.value,usuario=actor,
                comentario=f'Registro duplicado archivado; principal #{body.canonico_id}: '+body.motivo,
                evento_clave=f'regularizacion:{audit_id}',metadata={'principal_id':body.canonico_id,'referencia':body.referencia}))
            after=_json(_state('servicio',row,request=current['request'],ledger=current['ledger'],identity=current['owner'],periods=current['periods']))
            session.add(BitacoraCierre(id=audit_id,entidad_tipo='servicio',entidad_id=str(row.id),
                fuente_sha256=_hash(current['state']),resultado_sha256=_hash(after),accion='archivar_duplicado_legacy',
                antes_seguro=current['state'],despues_seguro=after,pendientes=[],actor_usuario_id=actor.id,referencia=body.referencia))
            return ResultadoDecision(200,{'servicio_id':row.id,'principal_id':body.canonico_id,'estado':'registro_duplicado_archivado'})
    return await ejecutar(db,actor_id=actor.id,clave=clave,metodo='POST',ruta=f'/servicios/{service_id}/regularizacion/archivar-duplicado',
        payload=body.model_dump(mode='json'),decidir=decide,target_tipo='servicio',target_id=service_id)
