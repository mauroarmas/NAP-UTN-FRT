"""Declarative creation and short job dispatch; guest strategy owns safe startup.

No installer runs in the API/worker. A persisted dispatch intention can only be
observed after a lost reply, never sent a second time by a new lease holder.
"""
from uuid import UUID

from sqlalchemy import select,func

from app.models.intento_despliegue import IntentoDespliegue
from app.services import identidad_infra_service as identities
from app.services import operacion_service as operations
from app.services.application_job_client import ApplicationJobClient
from app.services.consola_operacion_service import emitir_hito
from app.services.infraestructura_io import InfraNoVerificable
from app.services.perfiles_service import validar_asignacion_aplicacion
from app.utils.clock import clock
from app.utils.errors import error
from app.utils.secretos import configured_keyring
from infra.applications.job.protocol import (PROTOCOL,JobError,canonical,parse_request,
    parse_response,fingerprint)


def wire(operation,attempt,identity,*,action):
    assignment=operation.contexto_seguro['asignacion']
    nonce=configured_keyring().decrypt(identity.nonce_cifrado,context=f'infra:{identity.resource_uuid}:nonce')
    return {'protocol':PROTOCOL,'action':action,'operation_id':str(operation.id),
        'operacion_raiz_id':str(attempt.operacion_raiz_id),'intento_id':str(attempt.id),
        'execution_id':str(attempt.execution_id),'lease_generation':operation.lease_generation,
        'cluster_uuid':identity.cluster_id,'node':identity.nodo,'vmid':identity.vmid,
        'resource_uuid':str(identity.resource_uuid),'pool':identity.pool_catedra,'nonce':nonce,
        'configuracion_sha256':assignment['configuracion_sha256'],'perfil':assignment['perfil']}


async def preparar(sessions,lease,*,pve,runner):
    from app.services import orquestacion_service as flow
    op,_,_,pedido,_=await flow._view(sessions,lease)
    assignment=op.contexto_seguro['asignacion'];node=op.contexto_seguro['destino']['nodo']
    client=runner if runner is not None else ApplicationJobClient()
    request={'protocol':PROTOCOL,'action':'profiles'}
    reply=parse_response(canonical(await client.execute(request,node=node)),request=request)
    if not reply['ok'] or not any(all(profile.get(k)==v for k,v in assignment['perfil'].items())
            and profile['estado']=='habilitado' for profile in reply['data']['profiles']):
        raise error(409,'perfil_aplicacion_no_disponible','El nodo todavía no admite esta aplicación')
    from app.services.pool_catedra_service import asegurar
    async with sessions() as db:await asegurar(db,pedido.catedra_id,pve=pve)
    async with flow._locked(sessions,lease) as (db,op,identity,service,pedido,ledger):
        if (ledger is None or pedido is None or ledger.liberado_at is not None
                or not await flow._coverage(db,op,pedido,service)
                or ledger.expira_at and flow.db_utc(ledger.expira_at)<=clock.now()):
            raise error(409,'vigencia_no_habilitada','La reserva o vigencia no habilita la creación')
        await validar_asignacion_aplicacion(db,pedido)
        if op.contexto_seguro['asignacion']!=pedido.asignacion_snapshot or op.contexto_seguro['destino']!=pedido.destino_snapshot:
            raise error(409,'decision_no_vigente','La configuración aprobada cambió')
        identity=await identities.reclamar(db,op,pve=pve)
        ledger.identidad_infraestructura_id=identity.id
        attempt=await db.scalar(select(IntentoDespliegue).where(IntentoDespliegue.operacion_id==op.id).with_for_update())
        if attempt is None:
            root=op.operacion_raiz_id or op.id
            number=(await db.scalar(select(func.max(IntentoDespliegue.numero)).where(IntentoDespliegue.operacion_raiz_id==root)) or 0)+1
            attempt=IntentoDespliegue(operacion_id=op.id,operacion_raiz_id=root,numero=number,
                identidad_infraestructura_id=identity.id,configuracion_sha256=assignment['configuracion_sha256'])
            db.add(attempt);await db.flush()
        elif attempt.identidad_infraestructura_id!=identity.id:raise InfraNoVerificable()
        public=wire(op,attempt,identity,action='start')
        public.update(configuracion=assignment['configuracion'],secreto_referencias=assignment['secretos'])
        from app.services.reserva_red_service import aplicar_asignacion
        instance=op.contexto_seguro['red_reservada']['instance']
        net0=aplicar_asignacion('name=eth0,bridge='+instance['bridge']+',ip=dhcp',instance)+',firewall=1'
        await flow._cas(db,lease,identidad_infraestructura_id=identity.id,contexto_seguro={
            **op.contexto_seguro,'red_preparada':net0,'job_fingerprint':fingerprint(public)})
        await emitir_hito(db,lease,hito='creando_recurso')
    return True


async def enviar_o_consultar(sessions,lease,*,pve,runner):
    from app.services import orquestacion_service as flow
    client=runner if runner is not None else ApplicationJobClient()
    op,identity,service,pedido,_=await flow._view(sessions,lease)
    observation=await identities.observar(identity,pve=pve)
    if observation.estado!='propia' or not flow._matches(observation.config,op.contexto_seguro['asignacion'],op.contexto_seguro['destino']):
        raise InfraNoVerificable()
    async with flow._locked(sessions,lease) as (db,op,identity,service,pedido,ledger):
        if not await flow._coverage(db,op,pedido,service):
            raise error(409,'vigencia_no_habilitada','La vigencia no habilita iniciar la instalación')
        await validar_asignacion_aplicacion(db,pedido)
        attempt=await db.scalar(select(IntentoDespliegue).where(IntentoDespliegue.operacion_id==op.id).with_for_update())
        if attempt is None:raise InfraNoVerificable()
        start=not op.contexto_seguro.get('application_job_requested',False)
        if start:
            from app.models.identidad_infraestructura import IdentidadInfraestructura
            active=await db.scalar(select(func.count()).select_from(IntentoDespliegue)
                .join(IdentidadInfraestructura,IntentoDespliegue.identidad_infraestructura_id==IdentidadInfraestructura.id)
                .where(IdentidadInfraestructura.cluster_id==identity.cluster_id,IdentidadInfraestructura.nodo==identity.nodo,
                    IntentoDespliegue.iniciado_at.is_not(None),IntentoDespliegue.estado.in_(['preparado','ejecutando','incierto'])))
            if active>=2:
                await emitir_hito(db,lease,hito='esperando_instalacion')
                if not await operations.ceder(db,lease,segundos=2):raise flow.LeasePerdido()
                return
        request=wire(op,attempt,identity,action='start' if start else 'status')
        expected=op.contexto_seguro['job_fingerprint']
        if start:
            if observation.status!='stopped':raise InfraNoVerificable()
            from app.services.secreto_despliegue_service import para_dispatch
            request.update(configuracion=op.contexto_seguro['asignacion']['configuracion'],
                secreto_referencias=op.contexto_seguro['asignacion']['secretos'],secretos=await para_dispatch(db,lease))
            if fingerprint(request)!=expected:raise InfraNoVerificable()
            await flow._cas(db,lease,contexto_seguro={**op.contexto_seguro,'application_job_requested':True})
            attempt.iniciado_at=clock.now()
            await emitir_hito(db,lease,hito='instalacion_solicitada')
        parse_request(canonical(request))
    # The intention and its console milestone are committed before SSH.
    try:
        response=await client.execute(request,expected_fingerprint=expected)
        response=parse_response(canonical(response),request=request)
        if not response['ok'] or response['data']['fingerprint']!=expected:raise JobError('UNCONFIRMED')
    except (JobError,TimeoutError,OSError):raise InfraNoVerificable(incierto=True) from None
    data=response['data']
    async with flow._locked(sessions,lease) as (db,op,identity,service,pedido,ledger):
        attempt=await db.scalar(select(IntentoDespliegue).where(IntentoDespliegue.operacion_id==op.id).with_for_update())
        if attempt is None:raise InfraNoVerificable()
        if attempt.node_boot_id is not None and str(attempt.node_boot_id)!=data['node_boot_id']:raise InfraNoVerificable(incierto=True)
        if attempt.estado in {'confirmado','fallido'} and attempt.estado!=data['estado']:raise InfraNoVerificable(incierto=True)
        attempt.runner_job_id=str(attempt.execution_id);attempt.node_boot_id=UUID(data['node_boot_id'])
        attempt.estado=data['estado'];attempt.observado_at=clock.now()
        if attempt.iniciado_at is None:attempt.iniciado_at=clock.now()
        if data['estado']=='confirmado':await emitir_hito(db,lease,hito='comprobando')
        # Confirmation of the node is not yet delivery; console ingestion and
        # independent access probes must precede that transition (T033/T034).
        await flow._cas(db,lease,contexto_seguro={**op.contexto_seguro,'application_job_estado':data['estado']})
    await flow._defer(sessions,lease,uncertain=data['estado']=='incierto',code=data['error_codigo'])


async def ingerir_trabajo(sessions,lease,*,runner=None,pve=None,probe=None):
    """A bounded console tick. It cannot start or restart an installation."""
    from app.services import orquestacion_service as flow
    from app.services.consola_operacion_service import ingerir_y_confirmar
    client=runner if runner is not None else ApplicationJobClient()
    async with flow._locked(sessions,lease) as (db,op,identity,service,pedido,ledger):
        attempt=await db.scalar(select(IntentoDespliegue).where(IntentoDespliegue.operacion_id==op.id))
        if attempt is None or identity is None or not op.contexto_seguro.get('application_job_requested'):raise InfraNoVerificable()
        request=wire(op,attempt,identity,action='read')
        request.update(after=attempt.ultimo_source_seq,limit_bytes=65536)
        expected=op.contexto_seguro['job_fingerprint']
    response=parse_response(canonical(await client.execute(request,expected_fingerprint=expected)),request=request)
    if not response['ok'] or response['data']['fingerprint']!=expected:raise InfraNoVerificable(incierto=True)
    result=await ingerir_y_confirmar(sessions,lease,request=request,response=response,client=client)
    data=response['data'];finished=result['through_seq']>=data['last_source_seq']
    async with flow._locked(sessions,lease) as (db,op,identity,service,pedido,ledger):
        attempt=await db.scalar(select(IntentoDespliegue).where(IntentoDespliegue.operacion_id==op.id).with_for_update())
        attempt.estado=data['estado'];attempt.observado_at=clock.now()
        await flow._cas(db,lease,contexto_seguro={**op.contexto_seguro,'application_job_estado':data['estado'],
            'application_console_ack_pending':not result['ack_confirmed']})
        if finished and data['estado']=='confirmado':await emitir_hito(db,lease,hito='comprobando')
        if finished and data['estado']=='fallido' and result['ack_confirmed']:
            attempt.terminado_at=clock.now();attempt.error_codigo=data['error_codigo']
            await emitir_hito(db,lease,hito='fallo')
    if finished and data['estado']=='fallido' and result['ack_confirmed']:
        await flow._finish_failure(sessions,lease,data['error_codigo'] or 'instalacion_fallida')
    elif finished and data['estado']=='confirmado' and result['ack_confirmed']:
        from app.services.application_verification_service import verify
        await verify(sessions,lease,pve=pve,probe=probe)
    else:
        async with flow._locked(sessions,lease) as (db,op,identity,service,pedido,ledger):
            if data['estado']=='incierto' and ledger:ledger.estado='incierto'
            if not await operations.ceder(db,lease,segundos=1,incierta=data['estado']=='incierto',error_codigo=data['error_codigo']):
                raise flow.LeasePerdido()
