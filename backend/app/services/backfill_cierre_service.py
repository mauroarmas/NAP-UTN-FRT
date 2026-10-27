"""Backfill conservador. Las ambigüedades quedan pendientes, nunca activadas."""
from copy import deepcopy
from datetime import date,datetime
import hashlib
import re
from uuid import UUID,uuid4

from sqlalchemy import select, insert
from sqlalchemy.orm import defer

from app.models.bitacora_cierre import BitacoraCierre
from app.models.compromiso_capacidad import CompromisoCapacidad
from app.models.identidad_infraestructura import IdentidadInfraestructura
from app.models.pedido import Pedido,PedidoHistorial
from app.models.vigencia import VigenciaAutorizada
from app.models.servicio import Servicio
from app.models.usuario import Usuario
from app.schemas.evidencia import canonical
from app.services import capacidad_service,inventario_service
from app.utils.clock import clock,db_utc
from app.utils.errors import error
from app.utils.secretos import configured_keyring,SecretError
from app.services.legado_cierre import cargar,limpiar,valor as legado

GIB=1024**3
VERSION=1


def _json(value):
    if isinstance(value,datetime): return db_utc(value).isoformat()
    if isinstance(value,UUID): return str(value)
    if isinstance(value,dict): return {k:_json(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)): return [_json(v) for v in value]
    return getattr(value,'value',value)


def _hash(value):
    return hashlib.sha256(canonical(_json(value)).encode()).hexdigest()


def _positive(values):
    return all(type(value) is int and value>0 for value in values)


def _state(kind,row,*,request=None,ledger=None,identity=None,periods=()):
    if kind=='usuario':
        return {'id':row.id,'mfa_activo':row.totp_habilitado,'inconsistente':row.habilitacion_inconsistente,
            'auth_version':row.auth_version,'legado_sha256':_hash(legado(row,'totp_secret')),
            'factor_cifrado_sha256':_hash(row.totp_secret_encrypted)}
    if kind=='pedido':
        return {'id':row.id,'estado':row.estado.value,'revision':row.revision,'revision_decision':row.revision_decision,'catedra_id':row.catedra_id,
            'template_id':row.template_id,'definicion_version_id':str(row.definicion_version_id) if row.definicion_version_id else None,'tipo_pedido':row.tipo.value,'vigencia_tipo':row.vigencia_tipo.value,
            'anio_lectivo':row.anio_lectivo,'servicio_renovado_id':row.servicio_id,
            'modelo':row.modelo_servicio.value,'asignacion':row.asignacion_snapshot,
            'decision_sha256':_hash(row.decision_snapshot),'periodos':_period_state(periods),
            'cantidades_autorizadas':[legado(row,k) for k in ['reserva_vcpus','reserva_ram_mb','reserva_disk_gb']],
            'vigencia_desde':row.vigencia_desde.isoformat() if row.vigencia_desde else None,
            'vigencia_hasta':row.vigencia_hasta.isoformat() if row.vigencia_hasta else None,
            'interpretacion_fechas_academicas':'legado_sin_completar_periodos'}
    return {'id':row.id,'catedra_id':row.catedra_id,'pedido_id':row.pedido_id,'vmid':row.proxmox_vmid,
        'nodo':row.proxmox_node,'tipo':row.tipo,'estado':row.estado.value,'deleted_at':row.deleted_at,
        'definicion_version_id':str(row.definicion_version_id) if row.definicion_version_id else None,
        'identidad_id':str(row.identidad_infraestructura_id) if row.identidad_infraestructura_id else None,
        'asignacion':row.asignacion_snapshot,'modelo':row.modelo_servicio,'nombre':row.nombre_snapshot,
        'cantidades':[row.vcpus_asignados,row.ram_asignada_mb,row.disk_asignado_gb],
        'vigencia_hasta':row.vence_at,'acceso':row.disponibilidad_aplicacion,
        'periodos':_period_state(periods),
        'identidad':{'resource_uuid':str(identity.resource_uuid),'cluster':identity.cluster_id,
            'vmid':identity.vmid,'nodo':identity.nodo,'pool':identity.pool_catedra,
            'nonce_cifrado_sha256':_hash(identity.nonce_cifrado),'servicio_id':identity.servicio_id,
            'ausencia_confirmada_at':identity.ausencia_confirmada_at,
            'estado':identity.estado,'definition_sha256':identity.definition_sha256,'bundle_sha256':identity.bundle_sha256} if identity else None,
        'legado_sha256':_hash(legado(row,'credenciales_acceso')),'pedido_sha256':_hash(_state('pedido',request)) if request else None,
        'ledger':_json({key:getattr(ledger,key) for key in ['id','pedido_id','servicio_id','identidad_infraestructura_id',
            'estado','revision','nodo','storage_id','storage_scope','vcpus_retenidos','ram_mb_retenida','disk_bytes_retenidos']}) if ledger else None}


def _period_state(periods):
    return [{'id':str(p.id),'pedido_id':p.pedido_id,'revision':p.revision_decision,'servicio_id':p.servicio_id,
        'inicio':p.inicio_at,'fin_exclusivo':p.fin_exclusivo_at,'revocada_at':p.revocada_at,
        'desde_local':p.desde_local.isoformat(),'hasta_local':p.hasta_local.isoformat(),'zona_horaria':p.zona_horaria,
        'sustituye_id':str(p.sustituye_id) if p.sustituye_id else None} for p in sorted(periods,key=lambda r:str(r.id))]


def _known_decision(request,history):
    """Fechas y asignación sólo de decisión congelada y su evento coincidente."""
    from app.services.vigencia_service import resolver_fechas
    try:
        snapshot=request.decision_snapshot
        event=history.get((request.id,f'decision:{request.revision_decision}:aprobada'))
        if (request.revision_decision<=0 or not event or not event.usuario_id or event.actor_tipo!='usuario'
            or snapshot['revision_decision']!=request.revision_decision
            or _hash(snapshot)!=_hash(event.decision_metadata)
            or (request.asignacion_snapshot and _hash(request.asignacion_snapshot)!=_hash(snapshot['asignacion']))):
            return None
        assignment=snapshot['asignacion']
        if not _positive([assignment[k] for k in ['vcpus','ram_mb','disk_gb']]): return None
        period=snapshot['vigencia']
        resolved=resolver_fechas(date.fromisoformat(period['desde']),date.fromisoformat(period['hasta']),period['zona_horaria'])
        start=datetime.fromisoformat(period['inicio_at'].replace('Z','+00:00'))
        end=datetime.fromisoformat(period['fin_exclusivo_at'].replace('Z','+00:00'))
        if start.tzinfo is None or end.tzinfo is None or start!=resolved.inicio_at or end!=resolved.fin_exclusivo_at:
            return None
        return {'asignacion':deepcopy(assignment),'desde':resolved.desde,'hasta':resolved.hasta,
            'zona':resolved.zona_horaria,'inicio':resolved.inicio_at,'fin':resolved.fin_exclusivo_at,
            'calendario_id':period.get('calendario_id'),'calendario_revision':period.get('calendario_revision'),
            'aprobado_por':event.usuario_id,'aprobado_at':db_utc(event.created_at)}
    except (ValueError,TypeError,KeyError,AttributeError): return None


async def _collect(db,*,sondear=False,pve=None,locked=False):
    def query(model):
        q=select(model).order_by(model.id)
        # Este ejecutor debe poder trabajar antes de aplicar 010. Los campos
        # nuevos no participan del backfill 009 ni se infieren del estado actual.
        if model in {CompromisoCapacidad, IdentidadInfraestructura}:
            q=q.options(defer(model.recurso_ensayo_id))
        if model is Pedido and hasattr(Pedido, "seleccion_oferta_snapshot"):
            q=q.options(defer(Pedido.seleccion_oferta_snapshot))
        return q.with_for_update().execution_options(populate_existing=True) if locked else q
    # Cantidades de servicios/pedidos, nunca millones de snapshots de métricas.
    users=list((await db.scalars(query(Usuario))).all())
    requests={r.id:r for r in (await db.scalars(query(Pedido))).all()}
    services=list((await db.scalars(query(Servicio))).all())
    await cargar(db,'usuarios',users)
    await cargar(db,'pedidos',list(requests.values()))
    await cargar(db,'servicios',services)
    ledgers={r.servicio_id:r for r in (await db.scalars(query(CompromisoCapacidad).where(CompromisoCapacidad.liberado_at.is_(None)))).all() if r.servicio_id}
    identities={r.id:r for r in (await db.scalars(query(IdentidadInfraestructura))).all()}
    periods=list((await db.scalars(query(VigenciaAutorizada))).all())
    decisions={(e.pedido_id,e.evento_clave):e for e in (await db.scalars(select(PedidoHistorial).where(
        PedidoHistorial.estado_nuevo=='aprobado'))).all()}
    history=list((await db.scalars(select(BitacoraCierre))).all())
    by_result={(h.entidad_tipo,h.entidad_id,h.resultado_sha256) for h in history}
    inventory=None
    if sondear:
        try: inventory=await inventario_service.leer(pve)
        except Exception: inventory=None
    duplicate_ids=set();by_vmid={}
    for service in services:
        vmid=service.proxmox_vmid
        if service.deleted_at is None and vmid and vmid.isascii() and vmid.isdecimal():
            by_vmid.setdefault(int(vmid),[]).append(service.id)
    for ids in by_vmid.values():
        if len(ids)>1: duplicate_ids.update(ids)
    entries=[]
    def add(kind,row,actions,pending,*,request=None,ledger=None,evidence=None,identity=None):
        related=[p for p in periods if p.pedido_id==row.id] if kind=='pedido' else [p for p in periods if p.servicio_id==row.id] if kind=='servicio' else []
        state=_json(_state(kind,row,request=request,ledger=ledger,identity=identity,periods=related));checksum=_hash(state)
        entry={'entidad':kind,'id':row.id,'fuente_sha256':checksum,'acciones':actions,
            'datos_actuales':state,'pendientes':pending,'procesado':(kind,str(row.id),checksum) in by_result,
            'retencion_propuesta':{'identidad_id':str(evidence['identity'].id),'nodo':evidence['nodo'],
                'storage':evidence['storage'],'scope':evidence['scope'],
                'vcpus':evidence['cantidades'][0],'ram_mb':evidence['cantidades'][1],
                'disk_bytes':evidence['cantidades'][2],'estado':'incierto'} if evidence and 'identity' in evidence else None}
        entries.append((entry,row,state,evidence))
    for user in users:
        if legado(user,'totp_secret') is not None:
            add('usuario',user,['cuarentena_y_cifrado_factor'],[])
    for request in requests.values():
        actions=[];pending=[];known=_known_decision(request,decisions)
        if known:
            previous=next((s for s in services if s.pedido_id==request.id),None)
            known['servicio_id']=previous.id if previous else request.servicio_id
        if request.asignacion_snapshot is None:
            if known: actions.append('recuperar_asignacion_auditada')
            elif _positive([legado(request,k) for k in ['reserva_vcpus','reserva_ram_mb','reserva_disk_gb']]):
                actions.append('conservar_cantidades_autorizadas');pending.append('definicion_y_vigencia_no_inferidas')
        missing=not any(p.pedido_id==request.id and p.revision_decision==request.revision_decision for p in periods)
        if (missing and request.estado.value in {'aprobado','en_despliegue','activo','error','suspendido'}
            and (request.revision_decision>0 or actions)):
            if known: actions.append('recuperar_periodo_decision_auditada')
            else: pending.append('vigencia_requiere_decision')
        if actions or pending: add('pedido',request,actions,pending,evidence={'period':known} if known else None)
    for service in services:
        request=requests.get(service.pedido_id);ledger=ledgers.get(service.id)
        identity=identities.get(service.identidad_infraestructura_id)
        actions=[];pending=[];evidence=None
        if legado(service,'credenciales_acceso') is not None: actions.append('cuarentena_credenciales_sin_entrega')
        if service.deleted_at is None:
            if not service.asignacion_snapshot: pending.append('asignacion_sin_regularizar')
            service_periods=[p for p in periods if p.servicio_id==service.id and p.revocada_at is None]
            if not service_periods: pending.append('vigencia_requiere_decision')
            elif service.vence_at is None: actions.append('proyectar_fin_autorizado')
            if service.id in duplicate_ids: pending.append('vmid_duplicado')
            if not identity or identity.servicio_id!=service.id:
                pending.append('identidad_requiere_decision')
            if not request: pending.append('pedido_historico_requiere_decision')
            if (ledger and ledger.estado=='incierto') or (identity and identity.estado=='incierta'):
                pending.append('capacidad_retenida_hasta_regularizacion')
            if not ledger:
                pending.append('ledger_requiere_inventario')
                if inventory and identity and request and service.id not in duplicate_ids and service.tipo=='lxc':
                    resource=inventory['recursos'].get(identity.vmid)
                    try:
                        owned=(resource and identity.servicio_id==service.id and identity.ausencia_confirmada_at is None
                            and str(identity.vmid)==str(int(service.proxmox_vmid)) and identity.nodo==service.proxmox_node
                            and identity.pool_catedra==f'catedra-{service.catedra_id}'
                            and capacidad_service._owned(resource,identity,inventory['cluster_id']))
                        scopes={scope for scope,_ in resource['volumenes']} if owned else set()
                        destinations=[(node,storage,scope) for (node,storage),scope in inventory['destinos'].items()
                            if node==identity.nodo and scope in scopes]
                        if not owned or len(scopes)!=1 or len(destinations)!=1: raise ValueError()
                        node,storage,scope=destinations[0]
                        quantities=[max(service.vcpus_asignados,resource['configurado_vcpus']),
                            max(service.ram_asignada_mb,resource['configurado_ram_mb']),
                            max(service.disk_asignado_gb*GIB,sum(resource['volumenes'].values()))]
                        if not _positive(quantities): raise ValueError()
                        evidence={'identity':identity,'nodo':node,'storage':storage,'scope':scope,'cantidades':quantities}
                        actions.append('crear_ledger_conservador_incierto')
                        pending.remove('ledger_requiere_inventario')
                        pending.append('capacidad_retenida_hasta_regularizacion')
                    except (ValueError,TypeError,KeyError,SecretError):
                        pending.append('propiedad_no_confirmada_sin_adopcion')
        if actions or pending: add('servicio',service,actions,pending,request=request,ledger=ledger,evidence=evidence,identity=identity)
    return entries,requests,ledgers,identities,periods


async def planificar(db,*,sondear=False,pve=None):
    entries,_,_,_,_=await _collect(db,sondear=sondear,pve=pve)
    return {'schema_version':VERSION,'tipo':'backfill_conservador_009','sondeo_solicitado':sondear,
        'creado_at':clock.now().isoformat(),'pasos':[entry for entry,_,_,_ in entries]}


async def aplicar(db,plan,*,operador,referencia,pve=None):
    if not isinstance(operador,str) or not operador.strip() or len(operador)>200 or not isinstance(referencia,str) or not referencia.strip() or len(referencia)>200:
        raise ValueError('Operador y referencia de la copia comprobada son obligatorios')
    if not isinstance(plan,dict) or plan.get('schema_version')!=VERSION or plan.get('tipo')!='backfill_conservador_009':
        raise ValueError('Plan de backfill incompatible')
    keyring=configured_keyring()  # Antes de cualquier escritura.
    # Red antes de locks; se vuelve a contrastar la misma marca/nonce. Nunca
    # aceptar observaciones suministradas en el JSON como prueba de propiedad.
    inspected,_,_,_,_=await _collect(db,sondear=bool(plan.get('sondeo_solicitado')),pve=pve)
    evidence={(e['entidad'],e['id']):obs for e,_,_,obs in inspected}
    expected={(e['entidad'],e['id']):e for e in plan.get('pasos',[])}
    if len(expected)!=len(plan.get('pasos',[])): raise ValueError('Entidades repetidas en el plan')
    inspected_map={(e['entidad'],e['id']):e for e,_,_,_ in inspected}
    if (set(expected)!=set(inspected_map) or any(expected[key].get('acciones')!=inspected_map[key]['acciones']
        or expected[key].get('retencion_propuesta')!=inspected_map[key]['retencion_propuesta']
        for key in expected)):
        raise error(409,'plan_desactualizado','La observación o acciones aplicables cambiaron; revisar un plan nuevo')
    async with capacidad_service.bloqueo_capacidad(db):
        entries,requests,ledgers,identities,periods=await _collect(db,locked=True)
        current={(e['entidad'],e['id']):e for e,_,_,_ in entries}
        if set(expected)!=set(current) or any(expected[key].get('fuente_sha256')!=current[key]['fuente_sha256'] for key in current):
            raise error(409,'plan_desactualizado','Los datos cambiaron; generar y revisar un plan nuevo')
        audit_pending=[];applied=0;skipped=0
        remaining={(entry['entidad'],entry['id']):entry['pendientes'] for entry,_,_,_ in entries}
        for entry,row,before,_ in entries:
            if entry['procesado']:
                skipped+=1;continue
            actions=list(entry['acciones']);pending=list(entry['pendientes']);quarantine={}
            kind=entry['entidad'];identity=uuid4()
            if kind=='usuario':
                original=legado(row,'totp_secret');quarantine['totp_secret']=original
                if row.totp_habilitado and not row.totp_secret_encrypted:
                    if isinstance(original,str) and re.fullmatch(r'[A-Z2-7]{16,64}',original):
                        row.totp_secret_encrypted=keyring.encrypt(original,context=f'totp:{row.id}')
                    else:
                        row.habilitacion_inconsistente=True;pending.append('recuperacion_factor_requerida')
                row.auth_version+=1
            elif kind=='pedido':
                known=(evidence.get((kind,row.id)) or {}).get('period')
                if 'recuperar_asignacion_auditada' in actions:
                    row.asignacion_snapshot=deepcopy(known['asignacion'])
                elif 'conservar_cantidades_autorizadas' in actions:
                    row.asignacion_snapshot={'origen':'legado_cantidades_autorizadas','template_id':row.template_id,
                        'nombre':f'Asignación histórica del pedido #{row.id}','modelo_servicio':row.modelo_servicio.value,
                        'vcpus':legado(row,'reserva_vcpus'),'ram_mb':legado(row,'reserva_ram_mb'),'disk_gb':legado(row,'reserva_disk_gb')}
                if 'recuperar_periodo_decision_auditada' in actions:
                    period=VigenciaAutorizada(pedido_id=row.id,revision_decision=row.revision_decision,
                        servicio_id=known['servicio_id'],modalidad=row.vigencia_tipo.value,
                        anio_lectivo=row.anio_lectivo,calendario_id=known['calendario_id'],calendario_revision=known['calendario_revision'],
                        desde_local=known['desde'],hasta_local=known['hasta'],zona_horaria=known['zona'],
                        inicio_at=known['inicio'],fin_exclusivo_at=known['fin'],aprobado_por=known['aprobado_por'],
                        aprobado_at=known['aprobado_at'],origen='backfill_auditado')
                    db.add(period);periods.append(period)
            else:
                if legado(row,'credenciales_acceso') is not None:
                    quarantine['credenciales_acceso']=deepcopy(legado(row,'credenciales_acceso'))
                    row.disponibilidad_aplicacion='no_verificada'
                if 'proyectar_fin_autorizado' in actions:
                    row.vence_at=max(db_utc(p.fin_exclusivo_at) for p in periods if p.servicio_id==row.id and p.revocada_at is None).replace(tzinfo=None)
                observation=evidence.get((kind,row.id))
                if observation is not None and row.id not in ledgers:
                    quantities=observation['cantidades'];owner=observation['identity']
                    # La identidad ya estaba ligada al servicio y fue probada.
                    # No crear UUID/nonce, completar hashes ni cambiar sus estados.
                    commitment=CompromisoCapacidad(pedido_id=row.pedido_id,servicio_id=row.id,
                        identidad_infraestructura_id=owner.id,nodo=observation['nodo'],
                        storage_id=observation['storage'],storage_scope=observation['scope'],
                        vcpus_retenidos=quantities[0],ram_mb_retenida=quantities[1],
                        disk_bytes_retenidos=quantities[2],estado='incierto')
                    # Core explicita únicamente columnas 009; no emitir columnas
                    # nullable nuevas del ORM sobre una copia todavía sin migrar.
                    values={key:getattr(commitment,key) for key in ['pedido_id','servicio_id',
                        'identidad_infraestructura_id','nodo','storage_id','storage_scope',
                        'vcpus_retenidos','ram_mb_retenida','disk_bytes_retenidos','estado']}
                    values.update(id=uuid4(),revision=1,creado_at=clock.now())
                    await db.execute(insert(CompromisoCapacidad.__table__).values(**values))
                    commitment=await db.scalar(select(CompromisoCapacidad).where(CompromisoCapacidad.id==values['id'])
                        .options(defer(CompromisoCapacidad.recurso_ensayo_id)))
                    ledgers[row.id]=commitment
                    actions.append('crear_ledger_conservador_incierto')
                    pending=[p for p in pending if p!='ledger_requiere_inventario']+['capacidad_retenida_hasta_regularizacion']
            token=keyring.encrypt(quarantine,context=f'cierre:{identity}:legado') if quarantine else None
            if token and keyring.decrypt(token,context=f'cierre:{identity}:legado')!=quarantine:
                raise SecretError('No se confirmó la cuarentena cifrada')
            if kind=='usuario' and quarantine: await limpiar(db,'usuarios',row,'totp_secret')
            if kind=='servicio' and quarantine: await limpiar(db,'servicios',row,'credenciales_acceso')
            audit_pending.append((identity,entry,row,before,pending,token))
            remaining[(kind,row.id)]=pending
            applied+=1
        await db.flush()
        for identity,entry,row,before,pending,token in audit_pending:
            after=_json(_state(entry['entidad'],row,request=requests.get(row.pedido_id) if entry['entidad']=='servicio' else None,
                ledger=ledgers.get(row.id) if entry['entidad']=='servicio' else None,
                identity=identities.get(row.identidad_infraestructura_id) if entry['entidad']=='servicio' else None,
                periods=[p for p in periods if p.pedido_id==row.id] if entry['entidad']=='pedido' else [p for p in periods if p.servicio_id==row.id] if entry['entidad']=='servicio' else []))
            db.add(BitacoraCierre(id=identity,entidad_tipo=entry['entidad'],entidad_id=str(row.id),
                fuente_sha256=entry['fuente_sha256'],resultado_sha256=_hash(after),accion='backfill_009_v1',
                antes_seguro=before,despues_seguro=after,pendientes=sorted(set(pending)),legado_cifrado=token,
                actor_institucional=operador.strip(),referencia=referencia.strip()))
        await db.flush()
        pending=sorted({p for values in remaining.values() for p in values})
        return {'aplicados':applied,'ya_procesados':skipped,'infraestructura_modificada':False,
            'requiere_regularizacion':bool(pending),'pendientes':pending}
