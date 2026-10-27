"""Automatic delivery after a final job AND a fresh authenticated TLS observation."""
from dataclasses import dataclass
import asyncio
from hashlib import sha256
import ssl

import httpx
from sqlalchemy import select

from app.config import get_settings
from app.models.intento_despliegue import IntentoDespliegue
from app.models.pedido import EstadoPedido
from app.models.servicio import EstadoServicio
from app.models.usuario import Usuario
from app.services import identidad_infra_service as identities
from app.services.application_target_service import destination
from app.services.consola_operacion_service import emitir_hito
from app.services.infraestructura_io import InfraNoVerificable
from app.services.application_proxy_service import NoCookieJar
from app.utils.clock import clock
from app.utils.secretos import configured_keyring


@dataclass(frozen=True)
class AccessObservation:
    host:str
    address:str
    port:int
    configuration_sha256:str
    status:int


async def probe_web(instance):
    try:
        async with asyncio.timeout(instance['access']['probe']['timeout_segundos']):
            return await _probe_web(instance)
    except TimeoutError:raise InfraNoVerificable() from None


async def _probe_web(instance):
    access=instance['access']
    if access['tipo']!='web':raise InfraNoVerificable()
    try:
        context=ssl.create_default_context(cafile=get_settings().application_gateway_ca_file)
        async with httpx.AsyncClient(verify=context,trust_env=False,follow_redirects=False,cookies=NoCookieJar(),
                timeout=httpx.Timeout(access['probe']['timeout_segundos'],connect=min(5,access['probe']['timeout_segundos']))) as client:
            url=httpx.URL(scheme='https',host=instance['address'],port=instance['port'],path=access['probe']['path'])
            async with client.stream('GET',url,headers={'Host':instance['host']+':'+str(instance['port']),'Accept-Encoding':'identity'},
                    extensions={'sni_hostname':instance['host']}) as reply:
                if reply.status_code not in access['probe']['estados']:raise InfraNoVerificable()
                count=0
                async for chunk in reply.aiter_bytes(chunk_size=4096):
                    count+=len(chunk)
                    if count>65536:raise InfraNoVerificable()
                return AccessObservation(instance['host'],instance['address'],instance['port'],
                    instance['configuration_sha256'],reply.status_code)
    except (httpx.HTTPError,OSError,ValueError):raise InfraNoVerificable() from None


async def verify(sessions,lease,*,pve=None,probe=None):
    from app.services import orquestacion_service as flow,operacion_service as operations
    from app.services import pedido_service,historial_service,notificacion_service
    from app.services.perfiles_service import validar_asignacion_aplicacion
    op,identity,service,pedido,_=await flow._view(sessions,lease)
    observed=await identities.observar(identity,pve=pve)
    if (observed.estado!='propia' or observed.status!='running'
            or not flow._matches(observed.config,op.contexto_seguro['asignacion'],op.contexto_seguro['destino'])):
        raise InfraNoVerificable(incierto=True)
    async with flow._locked(sessions,lease) as (db,op,identity,service,pedido,ledger):
        final=op.contexto_seguro.get('consola_job_final') or {}
        checks=set((final.get('resultado') or {}).get('comprobaciones',[]))
        attempt=await db.scalar(select(IntentoDespliegue).where(IntentoDespliegue.operacion_id==op.id))
        if (final.get('estado')!='confirmado' or (final.get('resultado') or {}).get('recurso_configurado') is not True
                or not {'aislamiento','runtime','salud','acceso_web'}<=checks
                or op.contexto_seguro.get('application_console_ack_pending',True)
                or attempt is None or attempt.ultimo_source_seq<final.get('last_source_seq',2**63)
                or attempt.runner_job_id!=str(attempt.execution_id) or not await flow._coverage(db,op,pedido,service)):
            raise InfraNoVerificable()
        # Only a fresh PVE observation can recover ownership certainty. This
        # does not deliver access or release the retained capacity commitment.
        identity.estado='materializada';identity.ownership_verificada_at=clock.now()
        _,instance=await destination(db,service,prepared=False)
        if instance['access']['tipo']!='web':raise InfraNoVerificable()
    result=await (probe or probe_web)(instance)  # Never hold SQL across network IO.
    if (type(result) is not AccessObservation or (result.host,result.address,result.port,result.configuration_sha256)!=
            (instance['host'],instance['address'],instance['port'],instance['configuration_sha256'])
            or result.status not in instance['access']['probe']['estados']):raise InfraNoVerificable()
    async with flow._locked(sessions,lease) as (db,op,identity,service,pedido,ledger):
        await validar_asignacion_aplicacion(db,pedido)
        _,current=await destination(db,service,prepared=False)
        if current!=instance or not await flow._coverage(db,op,pedido,service):raise InfraNoVerificable()
        attempt=await db.scalar(select(IntentoDespliegue).where(IntentoDespliegue.operacion_id==op.id).with_for_update())
        if op.contexto_seguro.get('application_console_ack_pending',True):raise InfraNoVerificable()
        now=clock.now()
        nonce=configured_keyring().decrypt(identity.nonce_cifrado,context=f'infra:{identity.resource_uuid}:nonce')
        service.acceso_metadata={'preparacion_id':str(op.id),'local_health':True,'automatic_access_verified':True,
            'configuracion_sha256':instance['configuration_sha256'],'nonce_sha256':sha256(nonce.encode()).hexdigest(),
            'host':instance['host'],'addresses':[instance['address']],'endpoint':instance['endpoint'],'port':instance['port'],
            'metodo':'https','probe_status':result.status,'probe_verified_at':now.isoformat()}
        before=service.estado.value
        service.estado=EstadoServicio.RUNNING;service.disponibilidad_aplicacion='utilizable'
        service.observado_at=service.verificado_at=service.acceso_red_verificado_at=now
        identity.estado='materializada';identity.ownership_verificada_at=now
        ledger.estado='materializado';ledger.expira_at=None
        ledger.vcpus_retenidos=op.contexto_seguro['asignacion']['vcpus']
        ledger.ram_mb_retenida=op.contexto_seguro['asignacion']['ram_mb']
        attempt.estado='confirmado';attempt.terminado_at=now
        actor=await db.get(Usuario,op.actor_usuario_id) if op.actor_usuario_id else None
        if pedido.estado!=EstadoPedido.EN_DESPLIEGUE:raise InfraNoVerificable()
        await pedido_service.transicionar(db,pedido.id,EstadoPedido.ACTIVO,usuario=actor,
            motivo='Instalación y acceso HTTPS comprobados automáticamente',operacion_id=op.id,
            evento_clave=f'operacion:{op.id}:entrega_aplicacion')
        db.add(historial_service.registrar_servicio(service.id,before,service.estado.value,
            comentario='Aplicación disponible; TLS y salud comprobados',operacion_id=op.id,
            evento_clave=f'operacion:{op.id}:entrega_aplicacion'))
        await emitir_hito(db,lease,hito='disponible')
        await notificacion_service.encolar_acceso_verificado(db,service,preparation_id=op.id)
        if not await operations.terminar(db,lease,estado='confirmada',fase='verificacion'):raise flow.LeasePerdido()
    return True
