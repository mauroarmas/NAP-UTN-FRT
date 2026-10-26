"""Cierre conservador: no liberar recursos mientras existan efectos inciertos."""
from datetime import timedelta
import logging
from time import monotonic
from uuid import uuid4,uuid5
from sqlalchemy import select,or_
from app.config import get_settings
from app.models.ensayo_preparacion import EnsayoPreparacion
from app.models.operacion_ensayo import OperacionEnsayo
from app.models.recurso_ensayo import RecursoEnsayo
from app.models.identidad_infraestructura import IdentidadInfraestructura
from app.models.compromiso_capacidad import CompromisoCapacidad
from app.models.evento_ensayo import EventoEnsayo
from app.services import ensayo_service as domain,identidad_infra_service as identities,infraestructura_io as io,builder_capacity_service,capacidad_service
from app.services.build_runner_client import BuildRunnerClient
from app.utils.clock import clock,db_utc


logger=logging.getLogger(__name__)


async def solicitar(db,row,*,motivo):
    if row.limpieza_estado=='confirmada':return
    if not row.cancelada_at:
        row.cancelada_at=clock.now();row.execution_generation+=1
    row.limpieza_estado='pendiente';row.motivo_cierre=motivo;row.revision+=1


async def procesar(sessions,*,builder=None,pve=None):
    # Reclamar un ensayo mediante lease de operación dedicado y generación local.
    async with sessions() as db:
        await capacidad_service.BloqueoCapacidad(db).__aenter__()
        row=await db.scalar(select(EnsayoPreparacion).where(EnsayoPreparacion.limpieza_estado.in_(['pendiente','en_curso']))
            .order_by(EnsayoPreparacion.creado_at).with_for_update(skip_locked=True).limit(1))
        if not row:return False
        now=clock.now()
        prior=(await db.scalars(select(OperacionEnsayo).where(OperacionEnsayo.ensayo_id==row.id,
            OperacionEnsayo.tipo!='limpiar',OperacionEnsayo.estado.in_(['pendiente','en_curso','incierta'])))).all()
        # Primero esperar al lease y al límite de transportes de efectos previos.
        for old in prior:
            if old.lease_until and db_utc(old.lease_until)>now:return False
            if old.dispatch_started_at and db_utc(old.dispatch_started_at)+timedelta(seconds=30)>now:return False
            if old.upid:
                # Una tarea PVE conocida todavía puede materializar un recurso.
                resource=await db.get(RecursoEnsayo,old.recurso_id) if old.recurso_id else None
                if resource and resource.identidad_infraestructura_id:
                    identity=await db.get(IdentidadInfraestructura,resource.identidad_infraestructura_id)
                    task=await io.consultar('get_task_status',identity.nodo,old.upid,pve=pve)
                    if task.estado!='presente' or task.valor.get('status')!='stopped':return False
            old.estado='fallida';old.lease_owner=None;old.lease_until=None
        op=await db.scalar(select(OperacionEnsayo).where(OperacionEnsayo.ensayo_id==row.id,OperacionEnsayo.tipo=='limpiar').order_by(OperacionEnsayo.created_at.desc()).limit(1).with_for_update())
        if op and op.lease_until and db_utc(op.lease_until)>now:return False
        if not op:
            await db.flush();op=domain.enqueue(db,row,kind='limpiar')
            await db.flush()
        owner=str(uuid4());op.lease_owner=owner;op.lease_generation+=1;op.lease_until=now+timedelta(seconds=90);op.estado='en_curso'
        token=(row.id,row.execution_generation,op.id,op.lease_generation,owner)
        row.limpieza_estado='en_curso';profile=get_settings().perfiles_ensayo[row.perfil_id]
        await db.commit()
    async def locked(db):
        # Orden único: capacidad global antes de la fila del ensayo.
        await capacidad_service.BloqueoCapacidad(db).__aenter__()
        trial=await domain.obtener(db,token[0])
        operation=await db.get(OperacionEnsayo,token[2],populate_existing=True)
        if trial.execution_generation!=token[1] or operation.lease_owner!=token[4] or operation.lease_generation!=token[3] or db_utc(operation.lease_until)<=clock.now():
            raise RuntimeError('lease_perdido')
        return trial,operation
    started=monotonic()
    try:
        async with sessions() as db:
            row,op=await locked(db);context=dict(op.contexto_seguro)
            request={'protocol':'nap-build-runner/1','ensayo_id':str(row.id),'generation':row.execution_generation,
                'operation_id':str(op.id),'action':'cancel'}
            await db.commit()
        if not context.get('builder_closed'):
            response=await (builder or BuildRunnerClient()).execute(request,host_id=profile.builder_id)
            if response.get('closed') is not True or response.get('status')!='cancelled':raise ValueError('cierre_no_confirmado')
            async with sessions() as db:
                row,op=await locked(db);row.cierre_remoto_confirmado_at=clock.now()
                context['builder_closed']=True;op.contexto_seguro=context;await db.commit()
        async with sessions() as db:
            row,op=await locked(db)
            resources=list((await db.scalars(select(RecursoEnsayo).where(RecursoEnsayo.ensayo_id==row.id))).all())
            target=next((r for r in resources if not r.ausencia_confirmada_at),None)
            if target and target.identidad_infraestructura_id:
                identity=await db.get(IdentidadInfraestructura,target.identidad_infraestructura_id)
                await db.commit();observation=await identities.observar(identity,pve=pve)
                if observation.estado=='ajena':raise ValueError('propiedad_no_confirmada')
                async with sessions() as current:
                    row,op=await locked(current);resource=await current.get(RecursoEnsayo,target.id)
                    current_identity=await current.get(IdentidadInfraestructura,identity.id)
                    if observation.estado=='ausente':
                        # Antes de declarar ausencia, descartar tareas de creación en vuelo del mismo VMID.
                        tasks=await io.consultar('get_node_tasks',identity.nodo,vmid=identity.vmid,
                            since=int(db_utc(identity.claimed_at).timestamp()),tipo='vzcreate',pve=pve)
                        if tasks.estado!='presente':raise ValueError('tarea_incierta')
                        for task in tasks.valor:
                            if not task.get('endtime'):
                                status=await io.consultar('get_task_status',identity.nodo,task['upid'],pve=pve)
                                if status.estado!='presente' or status.valor.get('status')!='stopped':raise ValueError('tarea_incierta')
                        identities.retirar(current_identity,observation);resource.ausencia_confirmada_at=clock.now();op.contexto_seguro={'builder_closed':True}
                        async with capacidad_service.bloqueo_capacidad(current):
                            ledger=await current.scalar(select(CompromisoCapacidad).where(CompromisoCapacidad.recurso_ensayo_id==resource.id,CompromisoCapacidad.liberado_at.is_(None)).with_for_update())
                            if ledger:
                                ledger.vcpus_retenidos=ledger.ram_mb_retenida=ledger.disk_bytes_retenidos=0;ledger.estado='liberado';ledger.liberado_at=clock.now();ledger.revision+=1
                    else:
                        ctx=op.contexto_seguro
                        if ctx.get('upid') and ctx.get('resource')==str(resource.id):
                            task=await io.consultar('get_task_status',identity.nodo,ctx['upid'],pve=pve)
                            if task.estado!='presente' or task.valor.get('status')!='stopped':
                                op.lease_owner=None;op.lease_until=None;await current.commit();return True
                            from app.services.proxmox_client import tarea_exitosa
                            if not tarea_exitosa(task.valor.get('exitstatus')):raise ValueError('eliminacion_fallida')
                            op.contexto_seguro={'builder_closed':True}
                        else:
                            method='stop_lxc' if observation.status=='running' else 'delete_lxc'
                            op.dispatch_started_at=clock.now();await current.commit()
                            upid=await io.enviar(method,identity.nodo,identity.vmid,pve=pve)
                            async with sessions() as last:
                                _,op=await locked(last);op.contexto_seguro={'builder_closed':True,'upid':upid,'resource':str(resource.id)}
                                op.lease_owner=None;op.lease_until=None;await last.commit()
                            return True
                    op.lease_owner=None;op.lease_until=None;await current.commit();return True
            if target:
                target.ausencia_confirmada_at=clock.now()
                ledger=await db.scalar(select(CompromisoCapacidad).where(CompromisoCapacidad.recurso_ensayo_id==target.id,CompromisoCapacidad.liberado_at.is_(None)))
                if ledger:
                    ledger.vcpus_retenidos=ledger.ram_mb_retenida=ledger.disk_bytes_retenidos=0;ledger.estado='liberado';ledger.liberado_at=clock.now();ledger.revision+=1
                op.lease_owner=None;op.lease_until=None;await db.commit();return True
            await db.commit()
        response=await (builder or BuildRunnerClient()).execute({**request,'action':'cleanup','operation_id':str(uuid5(token[2],'cleanup'))},host_id=profile.builder_id)
        if response.get('closed') is not True or response.get('status')!='succeeded':raise ValueError('limpieza_no_confirmada')
        if response.get('result',{}).get('retained_bytes',0)>0 and not row.artefacto_id:raise ValueError('artefacto_retenido_no_conciliado')
        async with sessions() as db:
            row,op=await locked(db)
            await builder_capacity_service.liberar(db,ensayo_id=row.id,host=get_settings().builder_hosts[profile.builder_id],confirmado=True)
            logger.info('ensayo_limpieza confirmada ensayo_id=%s duration_ms=%d',row.id,int((monotonic()-started)*1000))
            row.limpieza_estado='confirmada';row.revision+=1;op.estado='confirmada';op.lease_owner=None;op.lease_until=None
            db.add(EventoEnsayo(ensayo_id=row.id,operacion_id=op.id,evento_clave=f'limpieza:{row.revision}',nuevo=row.estado,actor_tipo='sistema',actor_id='ensayos',motivo='Recursos efímeros liberados',metadata_segura={}))
            await db.commit()
    except Exception as exc:
        logger.warning('ensayo_limpieza incierta ensayo_id=%s operation_id=%s error_type=%s duration_ms=%d',token[0],token[2],type(exc).__name__,int((monotonic()-started)*1000))
        async with sessions() as db:
            try:
                row,op=await locked(db);row.limpieza_estado='fallida';row.error_codigo='limpieza_no_confirmada';row.revision+=1
                op.estado='incierta';op.lease_until=None;op.lease_owner=None;await db.commit()
            except RuntimeError:await db.rollback()
    return True


async def tick(db):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    await capacidad_service.BloqueoCapacidad(db).__aenter__()
    rows=(await db.scalars(select(EnsayoPreparacion).where(EnsayoPreparacion.limpieza_estado!='confirmada').with_for_update())).all()
    for row in rows:
        if row.aviso_at and row.avisado_at is None and clock.now()>=db_utc(row.aviso_at) and not row.cancelada_at:
            from app.services.notificacion_service import encolar_aviso_ensayo
            await encolar_aviso_ensayo(db,row)
            row.avisado_at=clock.now()
        if row.expires_at and clock.now()>=db_utc(row.expires_at) and not row.cancelada_at:
            if row.publicacion_id is None and row.estado not in {'descartada','vencida'}:domain.transicionar(db,row,'vencida',motivo='Venció el ensayo')
            await solicitar(db,row,motivo='Plazo de ensayo finalizado')
    await db.commit()
    return {'afectados':int(await procesar(async_sessionmaker(db.bind,expire_on_commit=False)))}
