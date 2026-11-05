"""Decisiones de preparación: estados centrales, capacidad e historia indivisibles."""
from copy import deepcopy
from datetime import timedelta
import hashlib
from uuid import UUID,uuid4
from sqlalchemy import select,text
from app.config import get_settings
from app.models.definicion_servicio import DefinicionServicio
from app.models.ensayo_preparacion import EnsayoPreparacion
from app.models.recurso_ensayo import RecursoEnsayo
from app.models.operacion_ensayo import OperacionEnsayo
from app.models.evento_ensayo import EventoEnsayo
from app.models.compromiso_capacidad import CompromisoCapacidad
from app.models.evento_seguridad import EventoSeguridad
from app.services import biblioteca_service,capacidad_service,builder_capacity_service
from app.services.acceso_service import requiere_admin_actual
from app.services.idempotencia_service import ejecutar,ResultadoDecision
from app.services.build_runner_client import BuildRunnerClient
from app.schemas.definicion import digest
from app.utils.clock import clock,db_utc
from app.utils.errors import error

TRANSICIONES={
 'pendiente':{'resolviendo','fallida','incierta','descartada','vencida'},
 'resolviendo':{'esperando_confirmacion','fallida','incierta','descartada','vencida'},
 'esperando_confirmacion':{'construyendo','fallida','descartada','vencida'},
 'construyendo':{'ensayando','fallida','incierta','descartada','vencida'},
 'ensayando':{'lista_para_comprobar','fallida','incierta','descartada','vencida'},
 'lista_para_comprobar':{'comprobada','fallida','descartada','vencida'},
 'comprobada':{'descartada','vencida'},
 'incierta':{'resolviendo','construyendo','ensayando','fallida','descartada','vencida'},
 'fallida':{'pendiente','resolviendo','construyendo','ensayando','descartada','vencida'},
 'descartada':set(),'vencida':set()}


def presentar(row):
    return {key:(str(value) if isinstance(value,UUID) else value.isoformat() if hasattr(value,'isoformat') else deepcopy(value))
        for key in ['id','incorporacion_id','definicion_id','perfil_id','estado','revision','execution_generation',
            'creado_at','expires_at','aviso_at','avisado_at','entradas_resueltas','entradas_sha256',
            'artefacto_id','evidencia_id','publicacion_id','limpieza_estado','error_codigo','error_detalle_seguro']
        for value in [getattr(row,key)]}


def transicionar(db,row,nuevo,*,actor=None,motivo=None,operacion_id=None):
    if nuevo not in TRANSICIONES.get(row.estado,set()):raise error(409,'estado_incompatible','El ensayo no admite esta transición')
    previous=row.estado;row.estado=nuevo;row.revision+=1
    db.add(EventoEnsayo(ensayo_id=row.id,operacion_id=operacion_id,evento_clave=f'estado:{row.revision}',
        anterior=previous,nuevo=nuevo,actor_tipo='usuario' if actor else 'sistema',actor_id=str(actor.id) if actor else 'ensayos',motivo=motivo,metadata_segura={}))


async def obtener(db,identity,*,actor=None,revision=None):
    if actor is not None:await requiere_admin_actual(db,actor)
    row=await db.scalar(select(EnsayoPreparacion).where(EnsayoPreparacion.id==identity).with_for_update().execution_options(populate_existing=True))
    if not row:raise error(404,'ensayo_no_encontrado','Ensayo no encontrado')
    if revision is not None and row.revision!=revision:raise error(409,'revision_desactualizada','El ensayo cambió; actualizá su estado',revision=row.revision)
    return row


def enqueue(db,row,*,kind,actor=None,resource=None,context=None):
    op=OperacionEnsayo(id=uuid4(),ensayo_id=row.id,recurso_id=resource.id if resource else None,tipo=kind,
        actor_tipo='usuario' if actor else 'sistema',actor_id=str(actor.id) if actor else 'ensayos',
        idempotency_key=f'{kind}:{row.revision}:{resource.id if resource else "builder"}',
        contexto_seguro=context or {},deadline_at=row.expires_at)
    db.add(op);return op


def version_tuple(value):return tuple(int(part) for part in value.split('.'))


async def crear_revision(db,incorporacion_id,*,actor,data,clave):
    actor=await requiere_admin_actual(db,actor)
    async def decide(session):
        inc=await biblioteca_service.obtener(session,incorporacion_id,actor=actor,bloquear=True)
        if inc.revision!=data.revision_esperada:raise error(409,'revision_desactualizada','La incorporación cambió',revision=inc.revision)
        if inc.identidad_externa!='ct/drawio.sh':raise error(409,'adaptador_no_disponible','Esta aplicación no tiene preparación NAP')
        if session.bind.dialect.name=='postgresql':
            lock=int.from_bytes(hashlib.sha256(f'definicion:{data.codigo}:{data.version}'.encode()).digest()[:8],signed=True)
            await session.execute(text('SELECT pg_advisory_xact_lock(:lock)'),{'lock':lock})
        previous=await session.scalar(select(DefinicionServicio).where(DefinicionServicio.codigo==data.codigo,DefinicionServicio.version==data.version))
        if previous:
            if previous.incorporacion_id!=inc.id:raise error(409,'version_existente','La revisión ya pertenece a otra incorporación')
            return ResultadoDecision(200,{'id':str(previous.id),'codigo':previous.codigo,'version':previous.version,'revision':previous.revision,'estado':previous.estado})
        existing=await session.scalar(select(DefinicionServicio.id).where(DefinicionServicio.incorporacion_id==inc.id).limit(1))
        if existing and not data.base_definicion_id:raise error(422,'antecedente_requerido','Elegí la revisión antecedente')
        if data.base_definicion_id:
            base=await session.get(DefinicionServicio,data.base_definicion_id)
            if not base or base.incorporacion_id!=inc.id or base.codigo!=data.codigo or base.producto!='drawio' or version_tuple(data.version)<=version_tuple(base.version):
                raise error(422,'antecedente_incompatible','La nueva versión debe superar a su antecedente de la misma incorporación')
        row=DefinicionServicio(incorporacion_id=inc.id,base_definicion_id=data.base_definicion_id,codigo=data.codigo,version=data.version,
            producto='drawio',modelo_servicio='saas',tipo_recurso='lxc',manifest={},estado='borrador')
        session.add(row);await session.flush()
        session.add(EventoSeguridad(actor_usuario_id=actor.id,accion='crear_revision_biblioteca',resultado='completado',referencia=str(row.id)))
        return ResultadoDecision(201,{'id':str(row.id),'codigo':row.codigo,'version':row.version,'revision':row.revision,'estado':row.estado})
    return await ejecutar(db,actor_id=actor.id,clave=clave,metodo='POST',ruta=f'/biblioteca/incorporaciones/{incorporacion_id}/definicion',payload=data.model_dump(mode='json'),decidir=decide)


async def iniciar(db,definition_id,*,actor,data,clave,pve=None,builder=None):
    actor=await requiere_admin_actual(db,actor)
    async def decide(session):
        settings=get_settings();profile=settings.perfiles_ensayo.get(data.perfil_ensayo_id)
        if not profile:raise error(409,'ensayo_no_preparado','Configurar un perfil de ensayo institucional antes de preparar')
        host=settings.builder_hosts.get(profile.builder_id)
        if not host:raise error(409,'ensayo_no_preparado','Falta el host de construcción')
        identity=uuid4();operation=uuid4();transport=builder or BuildRunnerClient()
        try:
            space=await transport.execute({'protocol':'nap-build-runner/1','ensayo_id':str(identity),'operation_id':str(operation),
                'generation':1,'action':'status'},host_id=profile.builder_id)
            free=space['result']['free_bytes']
            if not space['result'].get('recipe_ready'):raise ValueError()
        except Exception:raise error(409,'ensayo_no_preparado','No se pudo verificar builder, base y receta instalados') from None
        async with capacidad_service.bloqueo_capacidad(session):
            definition=await session.scalar(select(DefinicionServicio).where(DefinicionServicio.id==definition_id).with_for_update().execution_options(populate_existing=True))
            if (not definition or definition.estado!='borrador' or definition.producto!='drawio' or definition.incorporacion_id!=data.incorporacion_id):
                raise error(409,'definicion_incompatible','Seleccioná un borrador Draw.io de esta incorporación')
            if definition.revision!=data.revision_esperada:raise error(409,'revision_desactualizada','La definición cambió')
            active=await session.scalar(select(EnsayoPreparacion.id).where(EnsayoPreparacion.definicion_id==definition_id,
                EnsayoPreparacion.estado.not_in(['descartada','vencida','fallida']),EnsayoPreparacion.publicacion_id.is_(None)))
            if active:raise error(409,'ensayo_en_curso','Ya hay un ensayo abierto',ensayo_id=str(active))
            panorama=await capacidad_service.panorama(session,pve=pve,destino={'nodo':profile.nodo,'storage':profile.storage})
            cost={'vcpus':2*profile.vcpus,'ram_mb':2*profile.ram_mb,'disk_gb':2*profile.disk_gb}
            if any(cost[k]>panorama['libre'][k] for k in cost) or cost['ram_mb']>panorama['ram_fisica_libre_mb']:
                raise error(409,'capacidad_insuficiente','No hay capacidad para los dos recursos del ensayo')
            now=clock.now();expiry=now+timedelta(hours=data.plazo_horas) if data.plazo_horas is not None else None
            row=EnsayoPreparacion(id=identity,incorporacion_id=data.incorporacion_id,definicion_id=definition_id,
                perfil_id=data.perfil_ensayo_id,estado='pendiente',revision=1,execution_generation=1,creado_por=actor.id,
                expires_at=expiry,aviso_at=max(now,expiry-timedelta(hours=1)) if expiry else None)
            session.add(row);await session.flush()
            if row.aviso_at and row.aviso_at<=now:
                from app.services.notificacion_service import encolar_aviso_ensayo
                await encolar_aviso_ensayo(session,row);row.avisado_at=now
            await builder_capacity_service.reservar(session,ensayo_id=row.id,host_id=profile.builder_id,host=host,free_bytes=free)
            for role in ['funcional_a','funcional_b']:
                resource=RecursoEnsayo(id=uuid4(),ensayo_id=row.id,rol=role,destino_snapshot={
                    'nodo':profile.nodo,'storage':profile.storage,'storage_scope':panorama['storage_scope'],'pool':profile.pool,
                    'network_profile_id':profile.network_profile_id,'vcpus':profile.vcpus,'ram_mb':profile.ram_mb,'disk_gb':profile.disk_gb})
                session.add(resource);await session.flush()
                session.add(CompromisoCapacidad(recurso_ensayo_id=resource.id,nodo=profile.nodo,storage_id=profile.storage,
                    storage_scope=panorama['storage_scope'],vcpus_retenidos=profile.vcpus,ram_mb_retenida=profile.ram_mb,
                    disk_bytes_retenidos=profile.disk_gb*1024**3,estado='reservado',expira_at=expiry))
            op=enqueue(session,row,kind='resolver',actor=actor,context={k:space['result'][k] for k in ['recipe_revision','input_ref','input_sha256']})
            session.add(EventoEnsayo(ensayo_id=row.id,evento_clave='creado',nuevo='pendiente',actor_tipo='usuario',actor_id=str(actor.id),metadata_segura={}))
            await session.flush()
            return ResultadoDecision(202,{**presentar(row),'operacion_id':str(op.id),'consulta':f'/api/v1/ensayos/{row.id}'})
    return await ejecutar(db,actor_id=actor.id,clave=clave,metodo='POST',ruta=f'/definiciones/{definition_id}/ensayos',payload=data.model_dump(mode='json'),decidir=decide)


async def accion(db,identity,*,actor,data,clave,action):
    actor=await requiere_admin_actual(db,actor)
    async def decide(session):
        row=await obtener(session,identity,actor=actor,revision=data.revision_esperada)
        if action=='reintentar-limpieza':
            if row.limpieza_estado!='fallida':raise error(409,'estado_incompatible','La limpieza no requiere reintento')
            row.limpieza_estado='pendiente';row.revision+=1
            return ResultadoDecision(202,{**presentar(row),'operacion_id':None,'consulta':f'/api/v1/ensayos/{row.id}'})
        if row.cancelada_at or row.estado in {'descartada','vencida'}:raise error(409,'ensayo_cerrado','El ensayo está cerrado')
        if row.expires_at and db_utc(row.expires_at)<=clock.now() and not row.publicacion_id:raise error(409,'ensayo_vencido','El ensayo venció; esperá su limpieza')
        if action=='confirmar-entradas':
            if row.estado!='esperando_confirmacion' or row.entradas_sha256!=data.entradas_sha256:raise error(409,'entradas_desactualizadas','Revisá las entradas fijadas actuales')
            row.confirmada_por=actor.id;row.confirmada_at=clock.now()
            transicionar(session,row,'construyendo',actor=actor)
            op=enqueue(session,row,kind='construir',actor=actor)
        elif action=='descartar':
            if row.publicacion_id:raise error(409,'oferta_publicada','Retirá la oferta por su acción propia; el ensayo publicado sólo se limpia')
            transicionar(session,row,'descartada',actor=actor,motivo=data.motivo)
            row.cancelada_at=clock.now();row.execution_generation+=1;row.limpieza_estado='pendiente';row.motivo_cierre=data.motivo
            op=None
        elif action=='reintentar':
            if row.estado not in {'incierta','fallida'}:raise error(409,'estado_incompatible','El ensayo no requiere recuperación')
            # Reconciliar operación original, no generar otro efecto bajo otra identidad.
            op=await session.scalar(select(OperacionEnsayo).where(OperacionEnsayo.ensayo_id==row.id,
                OperacionEnsayo.estado.in_(['incierta','fallida'])).order_by(OperacionEnsayo.created_at.desc()).limit(1).with_for_update())
            if not op:raise error(409,'operacion_no_recuperable','No hay operación para conciliar')
            row.execution_generation+=1;row.revision+=1
            if op.estado=='fallida':
                kind=op.tipo
                resume={'resolver':'resolviendo','construir':'construyendo','distribuir':'construyendo','crear':'ensayando','bootstrap':'ensayando'}.get(kind)
                if not resume:raise error(409,'operacion_no_recuperable','La operación necesita revisión')
                if row.estado!=resume:transicionar(session,row,resume,actor=actor,motivo='Reintento de fallo confirmado')
                await session.flush()
                op=enqueue(session,row,kind=kind,actor=actor,resource=await session.get(RecursoEnsayo,op.recurso_id) if op.recurso_id else None,context=deepcopy(op.contexto_seguro))
            else:
                op.estado='incierta';op.next_poll_at=clock.now();op.lease_until=None
        elif action=='reintentar-limpieza':
            if row.limpieza_estado!='fallida':raise error(409,'estado_incompatible','La limpieza no requiere reintento')
            row.limpieza_estado='pendiente';row.revision+=1;op=None
        else:raise error(422,'accion_invalida','Acción no permitida')
        await session.flush()
        return ResultadoDecision(202,{**presentar(row),'operacion_id':str(op.id) if op else None,'consulta':f'/api/v1/ensayos/{row.id}'})
    return await ejecutar(db,actor_id=actor.id,clave=clave,metodo='POST',ruta=f'/ensayos/{identity}/{action}',payload=data.model_dump(mode='json'),decidir=decide)


async def comprobar(db,identity,*,actor,data,clave):
    from app.services import evidencia_service,catalogo_service
    from app.models.artefacto_preparado import ArtefactoPreparado
    from app.schemas.definicion import validar_manifest
    actor=await requiere_admin_actual(db,actor)
    async def decide(session):
        await capacidad_service.BloqueoCapacidad(session).__aenter__()
        row=await obtener(session,identity,actor=actor,revision=data.revision_esperada)
        if row.estado!='lista_para_comprobar' or row.cancelada_at or (row.expires_at and db_utc(row.expires_at)<=clock.now()):raise error(409,'ensayo_no_comprobable','Completá los ensayos vigentes antes de comprobar')
        artifact=await session.get(ArtefactoPreparado,row.artefacto_id)
        evidence,document=await evidencia_service.obtener(session,data.evidencia_id,tipo='validacion_definicion',revalidar=True)
        if not artifact or evidence.sha256!=data.evidencia_sha256 or document['entorno']!='real':raise error(409,'evidencia_invalida','Se requiere evidencia real de estos artefactos')
        from app.models.identidad_infraestructura import IdentidadInfraestructura
        ids=list((await session.scalars(select(IdentidadInfraestructura.resource_uuid).join(RecursoEnsayo,RecursoEnsayo.identidad_infraestructura_id==IdentidadInfraestructura.id).where(RecursoEnsayo.ensayo_id==row.id))).all())
        if len(ids)!=2 or set(document['resultado']['instancias'])!=set(map(str,ids)):raise error(409,'evidencia_desactualizada','La evidencia debe identificar ambos recursos del ensayo')
        definition=await session.get(DefinicionServicio,row.definicion_id)
        if definition.estado!='borrador' or document['resultado']['definicion_id']!=str(definition.id):raise error(409,'definicion_incompatible','La evidencia no corresponde al borrador')
        result=document['resultado']
        if result['image_sha256']!=artifact.image_sha256 or result['recipe_sha256']!=artifact.bundle_sha256:
            raise error(409,'artefacto_incompatible','La evidencia no corresponde al artefacto')
        manifest=deepcopy(artifact.manifest)
        manifest['validation']={'result':'passed','validated_at':document['observado_at'],'evidence_id':str(evidence.id),
            'evidence_sha256':evidence.sha256,'cluster_uuid':result['cluster_uuid'],'pve_versions':result['pve_versions'],
            'instances_tested':len(result['instancias']),'checks':result['checks']}
        validar_manifest(manifest)
        definition.manifest=manifest
        definition.revision+=1
        await catalogo_service.comprobar_evidencia(session,definition)
        row.evidencia_id=evidence.id
        transicionar(session,row,'comprobada',actor=actor)
        enqueue(session,row,kind='distribuir',actor=actor,context={'validated_manifest':manifest})
        return ResultadoDecision(200,presentar(row))
    return await ejecutar(db,actor_id=actor.id,clave=clave,metodo='POST',ruta=f'/ensayos/{identity}/comprobar',payload=data.model_dump(mode='json'),decidir=decide)
