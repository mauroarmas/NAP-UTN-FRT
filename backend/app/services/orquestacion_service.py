"""Admisión local y ejecución durable; ningún endpoint espera una tarea PVE."""
from contextlib import asynccontextmanager
from datetime import timedelta
import re
import time

from sqlalchemy import select

from app.models.compromiso_capacidad import CompromisoCapacidad
from app.models.identidad_infraestructura import IdentidadInfraestructura
from app.models.operacion_infraestructura import OperacionInfraestructura
from app.models.pedido import Pedido, EstadoPedido
from app.models.servicio import Servicio, EstadoServicio
from app.models.usuario import Usuario
from app.models.vigencia import VigenciaAutorizada
from app.services import operacion_service as operations, identidad_infra_service as identities
from app.services import capacidad_service, bootstrap_service, historial_service, notificacion_service
from app.services.infraestructura_io import consultar, con_cliente, InfraNoVerificable
from app.services.inventario_service import integer, disk_size, marker
from app.services.acceso_service import requiere_acceso_catedra
from app.utils.clock import clock, db_utc
from app.utils.errors import error


class LeasePerdido(Exception):
    pass


@asynccontextmanager
async def _locked(sessions, lease):
    async with sessions() as db, db.begin():
        async with capacidad_service.bloqueo_capacidad(db):
            operation = await db.scalar(select(OperacionInfraestructura).where(*operations.condicion_lease(lease)).with_for_update())
            if operation is None:
                raise LeasePerdido()
            identity = await db.get(IdentidadInfraestructura, operation.identidad_infraestructura_id) if operation.identidad_infraestructura_id else None
            service = await db.get(Servicio, operation.servicio_id) if operation.servicio_id else None
            request = await db.get(Pedido, operation.pedido_id) if operation.pedido_id else None
            ledger = await db.scalar(select(CompromisoCapacidad).where(
                CompromisoCapacidad.servicio_id == service.id if service else CompromisoCapacidad.pedido_id == operation.pedido_id,
                CompromisoCapacidad.liberado_at.is_(None)).with_for_update())
            yield db, operation, identity, service, request, ledger


async def _cas(db, lease, **values):
    if not await operations.actualizar(db, lease, **values):
        raise LeasePerdido()


async def _view(sessions, lease):
    async with _locked(sessions, lease) as rows:
        return rows[1:]


async def _defer(sessions, lease, *, uncertain=False, code=None, message=None):
    async with _locked(sessions, lease) as (db, op, identity, service, request, ledger):
        if uncertain and ledger:
            ledger.estado = 'incierto'
        if uncertain and identity:
            identity.estado = 'incierta'
        if not await operations.ceder(db, lease, incierta=uncertain,
            segundos=min(30, 2 ** min(op.intento, 4)), error_codigo=code,
            error_detalle_seguro=message or ('Resultado pendiente de comprobación; se conserva el compromiso' if uncertain else None)):
            raise LeasePerdido()


async def _finish_failure(sessions, lease, code, *, absence=None, release_unsent=False):
    from app.services.pedido_service import transicionar
    async with _locked(sessions, lease) as (db, op, identity, service, request, ledger):
        if absence is not None and identity:
            identities.retirar(identity, absence)
        if ledger:
            if absence is not None or (release_unsent and op.dispatch_started_at is None and identity is None):
                ledger.vcpus_retenidos = ledger.ram_mb_retenida = ledger.disk_bytes_retenidos = 0
                ledger.estado, ledger.liberado_at = 'liberado', clock.now()
            else:
                ledger.estado = 'incierto'
        if identity and absence is None:
            identity.estado = 'incierta'
        if request and request.estado == EstadoPedido.EN_DESPLIEGUE:
            await transicionar(db, request.id, EstadoPedido.ERROR, motivo='La operación requiere revisión: ' + code,
                operacion_id=op.id, evento_clave=f'operacion:{op.id}:fallida')
            from app.models.catedra import Catedra
            category = await db.get(Catedra, request.catedra_id)
            cat_nombre = category.nombre if category else f'#{request.catedra_id}'
            await notificacion_service.encolar_aviso_pedido(db, request,
                evento=f'pedido:{request.id}:error:{op.id}', tipo='pedido_error_despliegue',
                asunto=f'[Error en Despliegue] Incidente en Pedido #{request.id} ({cat_nombre})',
                texto=f'La operación de despliegue del pedido #{request.id} ({cat_nombre}) falló ({code}) y requiere revisión.',
                destinatarios='ambos')
        if not await operations.terminar(db, lease, estado='fallida', error_codigo=code,
            error_detalle_seguro='La operación no se completó. Revisá el diagnóstico antes de reintentar'):
            raise LeasePerdido()


def _matches(config, assignment, destination):
    try:
        parts = config['rootfs'].split(',')
        size = next(part.split('=', 1)[1] for part in parts[1:] if part.startswith('size='))
        return (integer(config['cores'], minimum=1) == assignment['vcpus']
            and integer(config['memory'], minimum=1) == assignment['ram_mb']
            and parts[0].split(':')[0] == destination['storage']
            and disk_size(size) == assignment['disk_gb'] * 1024**3
            and integer(config.get('unprivileged', 0)) == 1
            and not any(re.fullmatch(r'mp\d+', field) for field in config))
    except (ValueError, KeyError, TypeError, StopIteration, AttributeError):
        return False


async def _coverage(db, op, request, service):
    if service:
        from app.services.vigencia_service import exigir_cobertura
        try:
            await exigir_cobertura(db, service.id, clock.now())
            return True
        except Exception as exc:
            if getattr(exc, 'status_code', None) == 409:
                return False
            raise
    periods = list((await db.scalars(select(VigenciaAutorizada).where(
        VigenciaAutorizada.pedido_id == op.pedido_id,
        VigenciaAutorizada.revision_decision == op.contexto_seguro.get('revision_decision'),
        VigenciaAutorizada.revocada_at.is_(None)))).all())
    return any(db_utc(p.inicio_at) <= clock.now() < db_utc(p.fin_exclusivo_at) for p in periods)


async def _prepare(sessions, lease, *, pve, runner):
    op, identity, service, request, ledger = await _view(sessions, lease)
    if op.tipo == 'desplegar':
        assignment = op.contexto_seguro['asignacion']
        if assignment.get('tipo') != 'lxc':
            await _finish_failure(sessions, lease, 'tipo_no_soportado', release_unsent=True)
            return False
        validated = await bootstrap_service.validar_preparacion(
            sessions=sessions, asignacion=assignment, destino=op.contexto_seguro['destino'], runner=runner, pve=pve)
        net0 = validated.get('net0') if isinstance(validated, dict) else None
        if not isinstance(net0, str) or not re.fullmatch(r'name=eth0,bridge=[A-Za-z][A-Za-z0-9_-]{0,14},ip=dhcp(?:,tag=\d{1,4})?', net0):
            raise error(409, 'red_no_preparada', 'Falta una red institucional validada')
        async with _locked(sessions, lease) as (db, current, _, current_service, current_request, current_ledger):
            if not current_ledger or not current_request or current_request.estado != EstadoPedido.EN_DESPLIEGUE:
                raise error(409, 'decision_no_vigente', 'La decisión de despliegue ya no está vigente')
            if not await _coverage(db, current, current_request, current_service) or (current_ledger.expira_at and db_utc(current_ledger.expira_at) <= clock.now()):
                raise error(409, 'vigencia_no_habilitada', 'La reserva o vigencia no habilita la creación')
            category_id = current_request.catedra_id
        from app.services.pool_catedra_service import asegurar
        async with sessions() as db:
            await asegurar(db, category_id, pve=pve)
        async with _locked(sessions, lease) as (db, op, identity, service, request, ledger):
            if not ledger or not request or request.estado != EstadoPedido.EN_DESPLIEGUE:
                raise error(409, 'decision_no_vigente', 'La decisión de despliegue ya no está vigente')
            if not await _coverage(db, op, request, service) or (ledger.expira_at and db_utc(ledger.expira_at) <= clock.now()):
                raise error(409, 'vigencia_no_habilitada', 'La reserva o vigencia no habilita la creación')
            op.contexto_seguro = {**op.contexto_seguro, 'preparacion_validada': validated}
            identity = await identities.reclamar(db, op, pve=pve)
            allocation = op.contexto_seguro.get('red_reservada')
            if allocation:
                net0 += ',hwaddr=' + allocation['instance']['mac_address']
            ledger.identidad_infraestructura_id = identity.id
            await _cas(db, lease, identidad_infraestructura_id=identity.id, fase='lista',
                contexto_seguro={**op.contexto_seguro, 'red_preparada': net0,
                    'preparacion_validada': validated})
    else:
        if service is not None and getattr(service.tipo, 'value', service.tipo) != 'lxc':
            await _finish_failure(sessions, lease, 'tipo_no_soportado')
            return False
        if not identity or identity.ausencia_confirmada_at or not ledger:
            await _finish_failure(sessions, lease, 'asignacion_sin_regularizar')
            return False
        if op.tipo == 'reparar' and service is None:
            observation = await identities.observar(identity, pve=pve)
            await _materialize(sessions, lease, observation)
            return True
        async with _locked(sessions, lease) as (db, op, identity, service, request, ledger):
            await _cas(db, lease, fase='lista')
    return True


async def _dispatch(sessions, lease, action, *, pve, after_dispatch):
    op, identity, service, request, ledger = await _view(sessions, lease)
    if not identity or identity.ausencia_confirmada_at:
        raise InfraNoVerificable()
    expected = identities.marca(identity)
    vmid, node = identity.vmid, identity.nodo
    assignment, destination = op.contexto_seguro['asignacion'], op.contexto_seguro['destino']
    config = None
    if action == 'crear':
        if assignment.get('tipo') != 'lxc' or not op.contexto_seguro.get('red_preparada'):
            raise error(422, 'configuracion_incompatible', 'La creación requiere LXC preparado')
        config = {'vmid': vmid, 'hostname': 'nap-' + str(identity.resource_uuid)[:12],
            'cores': assignment['vcpus'], 'memory': assignment['ram_mb'],
            'rootfs': f"{destination['storage']}:{assignment['disk_gb']}",
            'ostemplate': assignment['image']['volume_id'], 'net0': op.contexto_seguro['red_preparada'],
            'pool': identity.pool_catedra, 'description': identities.descripcion(identity),
            'unprivileged': 1, 'start': 1, 'force': 0, 'restore': 0}
    async with _locked(sessions, lease) as (db, op, current, service, request, ledger):
        if current.id != identity.id or op.fase not in {'lista', 'detencion_necesaria', 'eliminacion_necesaria'}:
            raise LeasePerdido()
        if action in {'crear', 'iniciar', 'reiniciar'} and not await _coverage(db, op, request, service):
            if action == 'crear':
                raise error(409, 'sin_cobertura_actual', 'La creación ya no tiene cobertura')
            action = 'detener'
        if action == 'crear' and (ledger is None or (ledger.expira_at and db_utc(ledger.expira_at) <= clock.now())):
            raise error(409, 'reserva_caducada', 'La reserva caducó antes del envío')
        deadline = time.monotonic() + max(0, (db_utc(op.lease_until) - clock.now()).total_seconds())
        await _cas(db, lease, fase='dispatch_started', dispatch_started_at=clock.now(), upid=None,
            deadline_at=clock.now() + timedelta(seconds=180 if action == 'crear' else 60),
            contexto_seguro={**op.contexto_seguro, 'accion_externa': action,
                'detencion_fuera_cobertura': action == 'detener' and op.tipo in {'desplegar', 'iniciar', 'reiniciar'}})
    # La marca previa al POST está confirmada. Si el proceso cae desde aquí,
    # el sucesor consulta tarea/recurso; nunca regresa a 'lista' ni reenvía.
    def send(client):
        if time.monotonic() >= deadline:
            raise LeasePerdido()
        if action != 'crear':
            actual = client.get_lxc_config(node, vmid)
            resources = client.get_cluster_resources('vm')
            matches = [r for r in resources if integer(r['vmid'], minimum=1) == vmid]
            if (marker(actual) != expected or len(matches) != 1 or matches[0].get('pool') != expected['pool']
                or matches[0].get('node') != node or matches[0].get('type') != 'lxc'):
                raise InfraNoVerificable()
            if action in {'iniciar', 'reiniciar'} and not _matches(actual, assignment, destination):
                raise InfraNoVerificable()
        if time.monotonic() >= deadline:
            raise LeasePerdido()
        if action == 'crear':
            return client.create_lxc(node, **config)
        method = {'iniciar': 'start_lxc', 'detener': 'stop_lxc', 'reiniciar': 'reboot_lxc', 'eliminar': 'delete_lxc'}[action]
        return getattr(client, method)(node, vmid)
    upid = await con_cliente(send, pve=pve, timeout=10, incierto=True)
    if after_dispatch:
        await after_dispatch(lease, upid)
    if not isinstance(upid, str) or not upid.startswith('UPID:') or len(upid) > 300:
        raise InfraNoVerificable(incierto=True)
    async with _locked(sessions, lease) as (db, op, identity, service, request, ledger):
        await _cas(db, lease, fase='tarea', upid=upid)


async def _materialize(sessions, lease, observation):
    async with _locked(sessions, lease) as (db, op, identity, service, request, ledger):
        if observation.estado != 'propia' or not _matches(observation.config, op.contexto_seguro['asignacion'], op.contexto_seguro['destino']):
            raise InfraNoVerificable()
        assignment = op.contexto_seguro['asignacion']
        if service is None:
            service = Servicio(catedra_id=request.catedra_id, pedido_id=request.id,
                template_id=assignment['template_id'], tipo='lxc', proxmox_vmid=str(identity.vmid), proxmox_node=identity.nodo,
                estado=EstadoServicio.RUNNING if observation.status == 'running' else EstadoServicio.STOPPED,
                hostname=observation.config.get('hostname'), modelo_servicio=assignment.get('modelo_servicio'),
                nombre_snapshot=assignment.get('nombre'), definicion_version_id=request.definicion_version_id,
                vcpus_asignados=assignment['vcpus'], ram_asignada_mb=assignment['ram_mb'], disk_asignado_gb=assignment['disk_gb'],
                asignacion_snapshot=assignment, identidad_infraestructura_id=identity.id,
                disponibilidad_aplicacion='no_verificada', deployed_at=clock.now().replace(tzinfo=None))
            db.add(service)
            await db.flush()
            request.servicio_id, identity.servicio_id, ledger.servicio_id = service.id, service.id, service.id
            periods = list((await db.scalars(select(VigenciaAutorizada).where(VigenciaAutorizada.pedido_id == request.id,
                VigenciaAutorizada.revision_decision == op.contexto_seguro['revision_decision']))).all())
            for period in periods:
                period.servicio_id = service.id
            service.vence_at = max(db_utc(p.fin_exclusivo_at) for p in periods).replace(tzinfo=None)
            db.add(historial_service.registrar_servicio(service.id, 'nuevo', service.estado.value,
                comentario='Infraestructura materializada; acceso pendiente de verificación', operacion_id=op.id,
                evento_clave=f'operacion:{op.id}:materializada', metadata=historial_service.asignacion_historica(service)))
        identity.estado, identity.ownership_verificada_at = 'materializada', clock.now()
        ledger.estado, ledger.expira_at = 'materializado', None
        await _cas(db, lease, servicio_id=service.id, fase='bootstrap')


async def _cancel_obsolete_pause(sessions, lease, observation):
    async with _locked(sessions, lease) as (db, op, identity, service, request, ledger):
        if not (op.tipo == 'pausar' and op.actor_tipo == 'sistema' and op.actor_id_normalizado == 'vencimiento'
            and await _coverage(db, op, request, service)):
            return False
        if (observation.estado != 'propia' or observation.status != 'running'
            or not _matches(observation.config, op.contexto_seguro['asignacion'], op.contexto_seguro['destino'])):
            return False
        ledger.vcpus_retenidos = max(ledger.vcpus_retenidos, service.vcpus_asignados)
        ledger.ram_mb_retenida = max(ledger.ram_mb_retenida, service.ram_asignada_mb)
        db.add(historial_service.registrar_servicio(service.id, service.estado.value, service.estado.value,
            comentario='Pausa omitida: una aprobación posterior otorgó cobertura continua', operacion_id=op.id,
            evento_clave=f'operacion:{op.id}:sin_cambios', metadata=historial_service.asignacion_historica(service)))
        if not await operations.terminar(db, lease, estado='confirmada', fase='verificacion',
            contexto_seguro={**op.contexto_seguro, 'sin_cambios': True}):
            raise LeasePerdido()
        return True


async def _confirmed(sessions, lease, observation, *, preparation=None):
    async with _locked(sessions, lease) as (db, op, identity, service, request, ledger):
        if op.tipo == 'eliminar' and observation.estado == 'ausente':
            identities.retirar(identity, observation)
            service.deleted_at = clock.now().replace(tzinfo=None)
            new_state = EstadoServicio.STOPPED
            ledger.vcpus_retenidos = ledger.ram_mb_retenida = ledger.disk_bytes_retenidos = 0
            ledger.estado, ledger.liberado_at = 'liberado', clock.now()
        else:
            if observation.estado != 'propia' or service is None:
                raise InfraNoVerificable()
            action = op.contexto_seguro.get('accion_externa', 'bootstrap')
            stopped = action == 'detener'
            if observation.status != ('stopped' if stopped else 'running'):
                raise InfraNoVerificable()
            if not stopped and not _matches(observation.config, op.contexto_seguro['asignacion'], op.contexto_seguro['destino']):
                raise InfraNoVerificable()
            new_state = EstadoServicio.PAUSED if stopped and (op.tipo == 'pausar' or op.contexto_seguro.get('detencion_fuera_cobertura')) else (EstadoServicio.STOPPED if stopped else EstadoServicio.RUNNING)
            ledger.vcpus_retenidos = 0 if stopped else op.contexto_seguro['asignacion']['vcpus']
            ledger.ram_mb_retenida = 0 if stopped else op.contexto_seguro['asignacion']['ram_mb']
            ledger.estado, ledger.expira_at = 'materializado', None
            identity.estado, identity.ownership_verificada_at = 'materializada', clock.now()
            if preparation:
                service.acceso_metadata = preparation.get('acceso_metadata')
                # Una preparación nueva sí requiere nueva prueba de red. Un
                # stop/start del mismo guest no borra la entrega ya acreditada;
                # el revelado sigue exigiendo running, cobertura y pertenencia.
                service.disponibilidad_aplicacion = 'no_verificada'
            if new_state == EstadoServicio.PAUSED:
                service.pausado_auto_at = clock.now().replace(tzinfo=None)
            elif new_state == EstadoServicio.RUNNING:
                service.pausado_auto_at = service.pausa_programada_at = service.aviso_pausa_at = None
        before = service.estado.value
        service.estado, service.observado_at = new_state, clock.now()
        if request:
            from app.services.pedido_service import transicionar
            target = (EstadoPedido.SUSPENDIDO if new_state == EstadoServicio.PAUSED
                and request.estado == EstadoPedido.ACTIVO else EstadoPedido.ACTIVO
                if new_state == EstadoServicio.RUNNING and request.estado == EstadoPedido.SUSPENDIDO else None)
            if target:
                actor = await db.get(Usuario, op.actor_usuario_id) if op.actor_usuario_id else None
                await transicionar(db, request.id, target, usuario=actor,
                    motivo=op.motivo or ('Efecto confirmado: ' + op.tipo), operacion_id=op.id,
                    evento_clave=f'operacion:{op.id}:pedido_confirmado')
        db.add(historial_service.registrar_servicio(service.id, before, new_state.value,
            comentario='Efecto de infraestructura confirmado: ' + op.tipo, operacion_id=op.id,
            evento_clave=f'operacion:{op.id}:confirmada', metadata=historial_service.asignacion_historica(service)))
        if not await operations.terminar(db, lease, estado='confirmada', fase='verificacion'):
            raise LeasePerdido()


async def procesar_lease(sessions, lease, *, pve=None, runner=None, after_dispatch=None):
    """Un tick acotado: las tareas largas ceden el lease para próximo polling."""
    from app.services.reconciliacion_service import recuperar_upid
    try:
        for _ in range(8):
            op, identity, service, request, ledger = await _view(sessions, lease)
            if op.fase == 'preparacion':
                if not await _prepare(sessions, lease, pve=pve, runner=runner):
                    return
                continue
            if op.fase in {'lista', 'detencion_necesaria', 'eliminacion_necesaria'}:
                if op.fase == 'lista' and op.tipo == 'pausar' and op.actor_tipo == 'sistema' and op.actor_id_normalizado == 'vencimiento':
                    observation = await identities.observar(identity, pve=pve)
                    if await _cancel_obsolete_pause(sessions, lease, observation):
                        return
                if op.fase == 'detencion_necesaria':
                    action = 'detener'
                elif op.fase == 'eliminacion_necesaria':
                    action = 'eliminar'
                else:
                    action = {'desplegar': 'crear', 'iniciar': 'iniciar', 'reiniciar': 'reiniciar',
                        'detener': 'detener', 'pausar': 'detener', 'eliminar': 'eliminar', 'reparar': 'bootstrap'}[op.tipo]
                    if action == 'bootstrap':
                        async with _locked(sessions, lease) as (db, current, *rest):
                            await _cas(db, lease, fase='bootstrap')
                        continue
                    if op.tipo == 'eliminar':
                        observation = await identities.observar(identity, pve=pve)
                        if observation.estado == 'ausente':
                            await _confirmed(sessions, lease, observation)
                            return
                        if observation.estado != 'propia':
                            raise InfraNoVerificable()
                        if observation.status == 'running':
                            action = 'detener'
                await _dispatch(sessions, lease, action, pve=pve, after_dispatch=after_dispatch)
                continue
            if op.fase in {'dispatch_started', 'tarea'}:
                if not op.upid:
                    recovered = await recuperar_upid(op, identity, pve=pve)
                    if recovered is None:
                        await _defer(sessions, lease, uncertain=True, code='dispatch_no_confirmado')
                        return
                    async with _locked(sessions, lease) as (db, current, *rest):
                        await _cas(db, lease, fase='tarea', upid=recovered)
                    continue
                task = await consultar('get_task_status', identity.nodo, op.upid, pve=pve)
                if task.estado != 'presente' or not isinstance(task.valor, dict):
                    raise InfraNoVerificable()
                if task.valor.get('status') != 'stopped':
                    expired = op.deadline_at is None or clock.now() >= db_utc(op.deadline_at)
                    await _defer(sessions, lease, uncertain=expired, code='tarea_sin_resultado' if expired else None)
                    return
                observation = await identities.observar(identity, pve=pve)
                exitstatus = task.valor.get('exitstatus', '')
                if exitstatus != 'OK' and not (isinstance(exitstatus, str) and exitstatus.startswith('WARNINGS:')):
                    if op.tipo == 'eliminar' and op.contexto_seguro['accion_externa'] == 'eliminar' and observation.estado == 'ausente':
                        await _confirmed(sessions, lease, observation)
                        return
                    await _finish_failure(sessions, lease, 'tarea_fallida', absence=observation if observation.estado == 'ausente' else None)
                    return
                action = op.contexto_seguro['accion_externa']
                if op.tipo == 'eliminar' and action == 'detener':
                    if observation.estado != 'propia' or observation.status != 'stopped':
                        raise InfraNoVerificable()
                    async with _locked(sessions, lease) as (db, current, *rest):
                        await _cas(db, lease, fase='eliminacion_necesaria')
                    continue
                if action == 'crear':
                    await _materialize(sessions, lease, observation)
                    continue
                if action in {'iniciar', 'reiniciar'}:
                    async with _locked(sessions, lease) as (db, current, current_identity, current_service, current_request, current_ledger):
                        if not await _coverage(db, current, current_request, current_service):
                            await _cas(db, lease, fase='detencion_necesaria')
                            continue
                await _confirmed(sessions, lease, observation)
                return
            if op.fase == 'bootstrap':
                observation = await identities.observar(identity, pve=pve)
                if observation.estado != 'propia' or not _matches(observation.config, op.contexto_seguro['asignacion'], op.contexto_seguro['destino']):
                    raise InfraNoVerificable()
                async with _locked(sessions, lease) as (db, current, current_identity, current_service, current_request, current_ledger):
                    covered = await _coverage(db, current, current_request, current_service)
                    if not covered:
                        await _cas(db, lease, fase='detencion_necesaria')
                if not covered:
                    continue
                preparation = await bootstrap_service.preparar(sessions=sessions, servicio_id=service.id,
                    operacion_id=op.id, identidad_id=identity.id, runner=runner, lease=lease)
                if not isinstance(preparation, dict) or preparation.get('identity_verified') is not True or preparation.get('local_health') is not True:
                    await _finish_failure(sessions, lease, 'preparacion_no_confirmada')
                    return
                observation = await identities.observar(identity, pve=pve)
                # La preparación tampoco habilita una entrega fuera de cobertura.
                async with _locked(sessions, lease) as (db, current, current_identity, current_service, current_request, current_ledger):
                    covered = await _coverage(db, current, current_request, current_service)
                    if not covered:
                        await _cas(db, lease, fase='detencion_necesaria')
                if not covered:
                    continue
                await _confirmed(sessions, lease, observation, preparation=preparation)
                return
            raise InfraNoVerificable()
        await _defer(sessions, lease)
    except LeasePerdido:
        return
    except InfraNoVerificable:
        await _defer(sessions, lease, uncertain=True, code='resultado_no_confirmado')
    except Exception as exc:
        if getattr(exc, 'status_code', None) in {409, 422}:
            op, *rest = await _view(sessions, lease)
            code = exc.detail.get('codigo', 'preparacion_no_disponible') if isinstance(exc.detail, dict) else 'preparacion_no_disponible'
            if code.startswith('pool_') and op.dispatch_started_at is None:
                await _defer(sessions, lease, code=code, message=exc.detail['mensaje'])
                return
            if op.dispatch_started_at is None:
                await _finish_failure(sessions, lease, code, release_unsent=True)
            else:
                await _finish_failure(sessions, lease, code)
            return
        raise


async def requiere_propio_o_admin(db, servicio, usuario):
    await requiere_acceso_catedra(db, usuario, servicio.catedra_id)


async def sincronizar_estados(db, servicios, *, usuario=None):
    # Lecturas ordinarias no consultan infraestructura ni modifican el negocio.
    from app.services.vigencia_service import anexar_cobertura
    await operations.anexar_operaciones(db, servicios)
    return await anexar_cobertura(db, servicios, usuario=usuario)


async def sincronizar_estado(db, servicio, *, usuario=None):
    return (await sincronizar_estados(db, [servicio], usuario=usuario))[0]


async def desplegar_pedido(db, pedido_id, admin, *, clave):
    from app.services.admision_service import desplegar
    return await desplegar(db, pedido_id, actor=admin, clave=clave)


async def iniciar_servicio(db, servicio_id, usuario, *, clave, motivo=None):
    from app.services.admision_service import iniciar
    return await iniciar(db, servicio_id, actor=usuario, clave=clave, motivo=motivo)


async def detener_servicio(db, servicio_id, usuario, *, clave):
    return await operations.admitir_orden(db, servicio_id, tipo='detener', usuario=usuario, clave=clave)


async def reiniciar_servicio(db, servicio_id, usuario, *, clave):
    return await operations.admitir_orden(db, servicio_id, tipo='reiniciar', usuario=usuario, clave=clave)


async def eliminar_servicio(db, servicio_id, admin, *, clave):
    return await operations.admitir_orden(db, servicio_id, tipo='eliminar', usuario=admin, clave=clave)


async def reintentar_despliegue(db, pedido_id, admin, *, clave, motivo=None):
    from app.services.reconciliacion_service import reintentar
    return await reintentar(db, pedido_id, actor=admin, clave=clave, motivo=motivo)
