"""Una fase durable por tick; llamadas externas fuera de las transacciones."""
from datetime import timedelta
import asyncio
from contextlib import suppress
import logging
from time import monotonic
from uuid import uuid4
from sqlalchemy import select,or_
from app.config import get_settings
from app.models.ensayo_preparacion import EnsayoPreparacion
from app.models.operacion_ensayo import OperacionEnsayo
from app.models.recurso_ensayo import RecursoEnsayo
from app.models.definicion_servicio import DefinicionServicio
from app.models.artefacto_preparado import ArtefactoPreparado
from app.models.identidad_infraestructura import IdentidadInfraestructura
from app.models.compromiso_capacidad import CompromisoCapacidad
from app.services import ensayo_service as domain,capacidad_service,artefacto_service,identidad_infra_service as identities,infraestructura_io as io
from app.services.build_runner_client import BuildRunnerClient
from app.services.guest_runner_client import GuestRunnerClient
from app.utils.clock import clock,db_utc


logger=logging.getLogger(__name__)


async def claim(db,owner):
    waiting=await db.scalar(select(EnsayoPreparacion).where(EnsayoPreparacion.estado=='esperando_confirmacion',
        EnsayoPreparacion.expires_at.is_(None),EnsayoPreparacion.cancelada_at.is_(None)).with_for_update(skip_locked=True).limit(1))
    if waiting:
        waiting.confirmada_por=waiting.creado_por;waiting.confirmada_at=clock.now()
        domain.transicionar(db,waiting,'construyendo',motivo='Continuación automática de la preparación')
        domain.enqueue(db,waiting,kind='construir');await db.flush()
    candidate=await db.scalar(select(OperacionEnsayo).join(EnsayoPreparacion,EnsayoPreparacion.id==OperacionEnsayo.ensayo_id).where(
        OperacionEnsayo.tipo!='limpiar',EnsayoPreparacion.cancelada_at.is_(None),or_(EnsayoPreparacion.expires_at.is_(None),EnsayoPreparacion.expires_at>clock.now()),OperacionEnsayo.estado.in_(['pendiente','en_curso','incierta']),
        OperacionEnsayo.next_poll_at<=clock.now(),or_(OperacionEnsayo.lease_until.is_(None),OperacionEnsayo.lease_until<=clock.now()))
        .order_by(OperacionEnsayo.created_at).limit(1))
    if not candidate:return None
    trial=await db.scalar(select(EnsayoPreparacion).where(EnsayoPreparacion.id==candidate.ensayo_id).with_for_update(skip_locked=True).execution_options(populate_existing=True))
    if not trial or trial.cancelada_at or (trial.expires_at and db_utc(trial.expires_at)<=clock.now()):return None
    op=await db.scalar(select(OperacionEnsayo).where(OperacionEnsayo.id==candidate.id).with_for_update().execution_options(populate_existing=True))
    if op.lease_until and db_utc(op.lease_until)>clock.now():return None
    op.lease_owner=str(owner);op.lease_generation+=1;op.lease_until=clock.now()+timedelta(seconds=90);op.intento+=1
    op.estado='en_curso'
    return op.id,str(owner),op.lease_generation,trial.execution_generation


async def owned(db,lease):
    await capacidad_service.BloqueoCapacidad(db).__aenter__()
    trial=await db.scalar(select(EnsayoPreparacion).join(OperacionEnsayo,OperacionEnsayo.ensayo_id==EnsayoPreparacion.id)
        .where(OperacionEnsayo.id==lease[0]).with_for_update(of=EnsayoPreparacion).execution_options(populate_existing=True))
    op=await db.scalar(select(OperacionEnsayo).where(OperacionEnsayo.id==lease[0]).with_for_update().execution_options(populate_existing=True))
    if (not trial or trial.cancelada_at or trial.execution_generation!=lease[3] or not op or op.lease_owner!=lease[1]
        or op.lease_generation!=lease[2] or not op.lease_until or db_utc(op.lease_until)<=clock.now()):
        raise RuntimeError('lease_perdido')
    return trial,op


def finish(op):
    op.estado='confirmada';op.lease_owner=None;op.lease_until=None;op.error_codigo=None


async def renovar_lease(sessions,lease):
    try:
        async with sessions() as db:
            _,op=await owned(db,lease)
            op.lease_until=clock.now()+timedelta(seconds=90)
            await db.commit()
        return True
    except RuntimeError:
        return False


async def _heartbeat(sessions,lease):
    while True:
        await asyncio.sleep(20)
        try:
            if not await renovar_lease(sessions,lease):return
        except Exception:
            logger.warning('ensayo_lease renovacion_no_confirmada operation_id=%s',lease[0])
            return


async def procesar_una(sessions,*,builder=None,pve=None,runner=None,owner=None):
    async with sessions() as db:
        lease=await claim(db,owner or uuid4());await db.commit()
    if not lease:return False
    heartbeat=asyncio.create_task(_heartbeat(sessions,lease))
    started=monotonic()
    logger.info('ensayo_operacion inicio operation_id=%s generation=%s',lease[0],lease[3])
    try:
        async with sessions() as db:
            trial,op=await owned(db,lease)
            kind=op.tipo;profile=get_settings().perfiles_ensayo[trial.perfil_id]
            artifact=await db.get(ArtefactoPreparado,trial.artefacto_id) if trial.artefacto_id else None
            resource=await db.get(RecursoEnsayo,op.recurso_id) if op.recurso_id else None
            if kind in {'resolver','construir','distribuir'}:
                context=op.contexto_seguro
                if kind=='resolver':
                    definition=await db.get(DefinicionServicio,trial.definicion_id)
                    request={'protocol':'nap-build-runner/1','operation_id':str(op.id),'ensayo_id':str(trial.id),
                        'generation':trial.execution_generation,'action':'resolve','recipe_id':'drawio-tomcat11-ubuntu-24.04-v1',
                        'recipe_revision':context['recipe_revision'],'input_ref':context['input_ref'],'input_sha256':context['input_sha256'],
                        'definition_id':str(definition.id),'definition_key':definition.codigo,'definition_version':definition.version}
                    if trial.estado in {'pendiente','incierta','fallida'}:domain.transicionar(db,trial,'resolviendo',operacion_id=op.id)
                else:
                    request={'protocol':'nap-build-runner/1','operation_id':str(op.id),'ensayo_id':str(trial.id),
                        'generation':trial.execution_generation,'action':'build' if kind=='construir' else 'stage',
                        'recipe_id':'drawio-tomcat11-ubuntu-24.04-v1','recipe_revision':trial.entradas_resueltas['recipe_revision'],
                        'input_ref':trial.entradas_resueltas['input_ref'],'input_sha256':trial.entradas_sha256}
                    if context.get('validated_manifest'):request['validated_manifest']=context['validated_manifest']
                poll=op.dispatch_started_at is not None
                if not poll:op.dispatch_started_at=clock.now()
                host_id=profile.builder_id
                await db.commit()
                # status no admite el manifiesto de stage: sólo consulta la operación ya enviada.
                status_request={k:v for k,v in request.items() if k!='validated_manifest'}
                response=await (builder or BuildRunnerClient()).execute({**status_request,'action':'status'} if poll else request,host_id=host_id)
                async with sessions() as current:
                    trial,op=await owned(current,lease)
                    if response['status'] in {'accepted','running','unknown','not_found'}:
                        op.estado='incierta' if response['status'] in {'unknown','not_found'} else 'pendiente'
                        op.lease_until=None;op.lease_owner=None;op.next_poll_at=clock.now()+timedelta(seconds=5)
                        if response['status'] in {'unknown','not_found'}:
                            trial.error_codigo='resultado_no_confirmado'
                            if trial.estado in {'resolviendo','construyendo','ensayando'}:domain.transicionar(current,trial,'incierta',operacion_id=op.id)
                    elif response['status']!='succeeded':
                        op.estado='fallida';op.lease_until=None;op.lease_owner=None
                        domain.transicionar(current,trial,'fallida',operacion_id=op.id,motivo='La construcción no se completó')
                    else:
                        result=response['result'];op.resultado={k:v for k,v in result.items() if k not in {'free_bytes'}};finish(op)
                        if kind=='resolver':
                            entries=result['entradas_resueltas']
                            if set(entries)!={'base_sha256','package_lock','runtime','recipe_revision','definition_id','definition_key','definition_version'}:raise ValueError('inputs_inseguros')
                            trial.entradas_resueltas={**entries,'input_ref':result['input_ref']};trial.entradas_sha256=result['input_sha256']
                            domain.transicionar(current,trial,'esperando_confirmacion',operacion_id=op.id)
                            if trial.expires_at is None:
                                trial.confirmada_por=trial.creado_por;trial.confirmada_at=clock.now()
                                domain.transicionar(current,trial,'construyendo',motivo='Preparación solicitada desde el alta simple',operacion_id=op.id)
                                domain.enqueue(current,trial,kind='construir')
                        elif kind=='construir':
                            artifact=await artefacto_service.registrar(current,trial,result)
                            await current.flush();domain.enqueue(current,trial,kind='distribuir')
                        else:
                            artifact=await current.get(ArtefactoPreparado,trial.artefacto_id)
                            await artefacto_service.replicas(current,artifact,result)
                            if op.contexto_seguro.get('validated_manifest'):
                                trial.revision+=1
                            else:
                                if trial.estado=='incierta':domain.transicionar(current,trial,'ensayando',operacion_id=op.id)
                                elif trial.estado=='construyendo':domain.transicionar(current,trial,'ensayando',operacion_id=op.id)
                                resources=(await current.scalars(select(RecursoEnsayo).where(RecursoEnsayo.ensayo_id==trial.id))).all()
                                await current.flush()
                                # Fijar ambas identidades/red en una transacción antes del primer create.
                                for item in resources:await identities.reclamar_ensayo(current,item,artifact,pve=pve)
                                for item in resources:domain.enqueue(current,trial,kind='crear',resource=item)
                    await current.commit()
                return True
            if kind=='crear':
                identity=await identities.reclamar_ensayo(db,resource,artifact,pve=pve)
                await db.commit()
                observation=await identities.observar(identity,pve=pve)
                async with sessions() as current:
                    trial,op=await owned(current,lease);resource=await current.get(RecursoEnsayo,op.recurso_id)
                    if observation.estado=='ajena':raise ValueError('propiedad_ajena')
                    if observation.estado=='propia':
                        if op.dispatch_started_at and not op.upid:
                            tasks=await io.consultar('get_node_tasks',identity.nodo,vmid=identity.vmid,
                                since=int(db_utc(identity.claimed_at).timestamp()),tipo='vzcreate',pve=pve)
                            if tasks.estado!='presente' or len(tasks.valor)!=1 or not tasks.valor[0].get('upid'):
                                await current.commit();return await release_poll(sessions,lease)
                            op.upid=tasks.valor[0]['upid']
                        if op.upid:
                            task=await io.consultar('get_task_status',identity.nodo,op.upid,pve=pve)
                            if task.estado!='presente' or task.valor.get('status')!='stopped':
                                await current.commit();return await release_poll(sessions,lease)
                            from app.services.proxmox_client import tarea_exitosa
                            if not tarea_exitosa(task.valor.get('exitstatus')):raise ValueError('creacion_fallida')
                        finish(op);await current.flush();domain.enqueue(current,trial,kind='bootstrap',resource=resource)
                        ledger=await current.scalar(select(CompromisoCapacidad).where(CompromisoCapacidad.recurso_ensayo_id==resource.id,CompromisoCapacidad.liberado_at.is_(None)))
                        ledger.estado='materializado'
                        current_identity=await current.get(IdentidadInfraestructura,identity.id)
                        current_identity.ownership_verificada_at=clock.now()
                        await current.commit();return True
                    if op.upid:
                        node=identity.nodo;upid=op.upid
                        await current.commit();task=await io.consultar('get_task_status',node,upid,pve=pve)
                        if task.estado!='presente' or task.valor.get('status')!='stopped':return await release_poll(sessions,lease)
                        from app.services.proxmox_client import tarea_exitosa
                        if not tarea_exitosa(task.valor.get('exitstatus')):raise ValueError('creacion_fallida')
                        return await release_poll(sessions,lease)
                    if op.dispatch_started_at:
                        # Una respuesta perdida no autoriza repetir create: consultar tareas del VMID.
                        tasks=await io.consultar('get_node_tasks',identity.nodo,vmid=identity.vmid,
                            since=int(db_utc(identity.claimed_at).timestamp()),tipo='vzcreate',pve=pve)
                        if tasks.estado=='presente' and len(tasks.valor)==1 and tasks.valor[0].get('upid'):
                            op.upid=tasks.valor[0]['upid']
                        await current.commit()
                        return await release_poll(sessions,lease)
                    destination=resource.destino_snapshot;allocation=destination['red_reservada']['instance']
                    network=get_settings().network_profiles[destination['network_profile_id']]
                    tag=f",tag={network['vlan_tag']}" if 'vlan_tag' in network else ''
                    from app.services.reserva_red_service import aplicar_asignacion
                    net0=aplicar_asignacion(f"name=eth0,bridge={network['bridge']},ip=dhcp"+tag,allocation)
                    params={'vmid':identity.vmid,'hostname':'nap-ensayo-'+identity.resource_uuid.hex[:12],
                        'cores':destination['vcpus'],'memory':destination['ram_mb'],'rootfs':f"{destination['storage']}:{destination['disk_gb']}",
                        'ostemplate':artifact.volume_id,'net0':net0,
                        'pool':identity.pool_catedra,'description':identities.descripcion(identity),'unprivileged':1,'start':1,'force':0,'restore':0}
                    op.dispatch_started_at=clock.now();await current.commit()
                upid=await io.enviar('create_lxc',identity.nodo,pve=pve,**params)
                async with sessions() as current:
                    _,op=await owned(current,lease);op.upid=upid;op.lease_until=None;op.lease_owner=None;op.next_poll_at=clock.now()+timedelta(seconds=2);await current.commit()
                return True
            if kind=='bootstrap':
                from app.services import ensayo_bootstrap_service
                request=await ensayo_bootstrap_service.preparar_peticion(db,trial,resource,artifact,op.id)
                op.dispatch_started_at=clock.now();await db.commit()
                response=await (runner or GuestRunnerClient()).execute(request)
                metadata=ensayo_bootstrap_service.confirmar(resource,request,response,op.id)
                async with sessions() as current:
                    trial,op=await owned(current,lease);resource=await current.get(RecursoEnsayo,op.recurso_id);resource.acceso_metadata=metadata;finish(op)
                    await current.flush()
                    resources=(await current.scalars(select(RecursoEnsayo).where(RecursoEnsayo.ensayo_id==trial.id))).all()
                    if trial.estado=='incierta':domain.transicionar(current,trial,'ensayando',operacion_id=op.id)
                    if all(r.acceso_metadata.get('local_health') for r in resources):domain.transicionar(current,trial,'lista_para_comprobar',operacion_id=op.id)
                    await current.commit()
                return True
            raise ValueError('operacion_no_admitida')
    except Exception as exc:
        logger.warning('ensayo_operacion incierta operation_id=%s error_type=%s duration_ms=%d',lease[0],type(exc).__name__,int((monotonic()-started)*1000))
        async with sessions() as db:
            try:
                trial,op=await owned(db,lease)
                op.estado='incierta';op.lease_until=None;op.lease_owner=None;op.next_poll_at=clock.now()+timedelta(seconds=30);op.error_codigo='ejecucion_no_confirmada'
                trial.error_codigo='ejecucion_no_confirmada'
                if trial.estado in {'resolviendo','construyendo','ensayando'}:domain.transicionar(db,trial,'incierta',operacion_id=op.id)
                await db.commit()
            except RuntimeError:await db.rollback()
        return True
    finally:
        heartbeat.cancel()
        with suppress(asyncio.CancelledError):await heartbeat
        logger.info('ensayo_operacion fin operation_id=%s generation=%s duration_ms=%d',lease[0],lease[3],int((monotonic()-started)*1000))


async def release_poll(sessions,lease):
    async with sessions() as db:
        _,op=await owned(db,lease);op.lease_owner=None;op.lease_until=None;op.next_poll_at=clock.now()+timedelta(seconds=2);await db.commit()
    return True
