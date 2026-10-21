"""Admisión transaccional compartida: capacidad antes de locks de recursos."""
from datetime import timedelta
from uuid import uuid4
import hashlib

from pydantic import ValidationError
from sqlalchemy import select

from app.models.pedido import Pedido, EstadoPedido, TipoPedido, VigenciaTipo
from app.models.servicio import Servicio, EstadoServicio
from app.models.identidad_infraestructura import IdentidadInfraestructura
from app.models.compromiso_capacidad import CompromisoCapacidad
from app.models.operacion_infraestructura import OperacionInfraestructura
from app.models.vigencia import VigenciaAutorizada
from app.schemas.asignacion import AprobacionEfectiva
from app.services.acceso_service import requiere_admin_actual, requiere_acceso_pedido, requiere_acceso_servicio, usuario_actual
from app.services.idempotencia_service import ejecutar, ResultadoDecision, safe_json
from app.services import capacidad_service, evaluacion_service
from app.utils.clock import clock, db_utc
from app.utils.errors import error

OPEN = ['pendiente', 'en_curso', 'incierta']


def expiracion_reserva(period, approval):
    return min(period.fin_exclusivo_at, max(approval, period.inicio_at) + timedelta(hours=24))


async def _request(db, identity):
    value = await db.scalar(select(Pedido).where(Pedido.id == identity).with_for_update().execution_options(populate_existing=True))
    if value is None or value.deleted_at:
        raise error(404, 'pedido_no_encontrado', 'Pedido no encontrado')
    return value


async def _ledger(db, identity):
    return await db.scalar(select(CompromisoCapacidad).where(CompromisoCapacidad.pedido_id == identity,
        CompromisoCapacidad.liberado_at.is_(None)).with_for_update().execution_options(populate_existing=True))


async def _open_operation(db, pedido):
    return await db.scalar(select(OperacionInfraestructura).where(OperacionInfraestructura.pedido_id == pedido.id,
        OperacionInfraestructura.estado.in_(OPEN)).with_for_update())


def operation_response(operation):
    return {'operation_id': str(operation.id), 'estado': operation.estado, 'tipo': operation.tipo,
        'pedido_id': operation.pedido_id, 'servicio_id': operation.servicio_id,
        'mensaje': 'Orden admitida. Su resultado todavía no está confirmado.'}


async def _queue_deploy(db, pedido, *, actor, clave, payload):
    previous = await _open_operation(db, pedido)
    if previous:
        raise error(409, 'operacion_en_curso', 'Ya existe una operación abierta', operation_id=str(previous.id))
    operation = OperacionInfraestructura(tipo='desplegar', pedido_id=pedido.id,
        actor_usuario_id=actor.id, actor_tipo='usuario', actor_id_normalizado=str(actor.id),
        idempotency_key=clave, request_hash=hashlib.sha256(safe_json(payload).encode()).hexdigest(),
        estado='pendiente', fase='preparacion', creado_at=clock.now(), updated_at=clock.now(), next_poll_at=clock.now())
    operation.contexto_seguro = {'catedra_id': pedido.catedra_id, 'revision_decision': pedido.revision_decision,
        'asignacion': pedido.asignacion_snapshot, 'destino': pedido.destino_snapshot,
        'vigencia': pedido.decision_snapshot['vigencia'], 'modelo_servicio': pedido.modelo_servicio.value}
    db.add(operation)
    await db.flush()
    from app.services.pedido_service import transicionar
    await transicionar(db, pedido.id, EstadoPedido.EN_DESPLIEGUE, usuario=actor,
        motivo='Despliegue admitido; pendiente de ejecución y verificación', operacion_id=operation.id,
        evento_clave=f'operacion:{operation.id}:admitida')
    return operation


async def aprobar(db, pedido_id, *, actor, payload, clave, pve=None):
    actor = await requiere_admin_actual(db, actor)
    await requiere_acceso_pedido(db, actor, pedido_id)
    try:
        body = payload if isinstance(payload, AprobacionEfectiva) else AprobacionEfectiva.model_validate(payload)
    except ValidationError:
        raise error(422, 'datos_invalidos', 'La aprobación requiere selección efectiva y evaluación vigente') from None
    normalized_payload = body.model_dump(mode='json', exclude_none=True)
    selected = {key: normalized_payload[key] for key in ['asignacion', 'vigencia']}
    if body.destino:
        selected['destino'] = normalized_payload['destino']

    async def decide(session):
        async with capacidad_service.bloqueo_capacidad(session):
            pedido = await _request(session, pedido_id)
            if pedido.estado != EstadoPedido.SOLICITADO:
                raise error(409, 'estado_incompatible', 'La solicitud ya fue resuelta o requiere correcciones')
            if await _open_operation(session, pedido):
                raise error(409, 'operacion_en_curso', 'El pedido tiene una operación abierta')
            evaluation, fingerprint, pedido, template, definition, period, image = await evaluacion_service.calcular(
                session, pedido_id, actor=actor, payload=selected, pve=pve, bloquear=True)
            evaluacion_service.verificar_token(body.capacidad_token, huella=fingerprint, actor_id=actor.id, pedido_id=pedido_id)
            if evaluation['restricciones_fisicas']:
                raise error(409, 'limite_fisico', 'La asignación no puede satisfacerse físicamente en ese destino',
                            restricciones=evaluation['restricciones_fisicas'])
            if evaluation['justificacion_requerida'] and not (body.justificacion_capacidad and body.justificacion_capacidad.strip()):
                raise error(409, 'justificacion_capacidad_requerida', 'Justificá la sobreasignación antes de confirmar', evaluacion=evaluation)
            if body.desplegar_inmediatamente and (pedido.tipo == TipoPedido.RENOVACION or clock.now() < period.inicio_at):
                raise error(409, 'inicio_futuro' if pedido.tipo == TipoPedido.ALTA else 'renovacion_sin_despliegue',
                            'La fecha inicial debe estar habilitada; una renovación solo registra condiciones')
            assignment = {**evaluation['seleccion']['asignacion'], 'nombre': template.nombre, 'tipo': template.tipo.value,
                'modelo_servicio': pedido.modelo_servicio.value,
                'image': {'volume_id': image, 'sha256': definition.manifest['image']['sha256'] if definition else None},
                'minimum_resources': definition.manifest['minimum_resources'] if definition else {'vcpus': 1, 'ram_mb': 128, 'disk_gb': 1}}
            if definition:
                assignment.update(definition_sha256=definition.manifest_sha256, definition_key=definition.codigo,
                    definition_version=definition.version, product=definition.producto,
                    bundle_sha256=definition.manifest['preparation']['bundle_sha256'])
            destination = {**evaluation['seleccion']['destino'], 'storage_scope': evaluation['storage_scope']}
            service = None
            if pedido.tipo == TipoPedido.RENOVACION:
                service = await session.scalar(select(Servicio).where(Servicio.id == pedido.servicio_id).with_for_update())
                if not service or service.deleted_at or service.catedra_id != pedido.catedra_id:
                    raise error(409, 'servicio_renovacion_invalido', 'El servicio original ya no admite esa renovación')
                # US5 amplía el flujo de modificación de períodos. Sin snapshot
                # regularizado no se inventa una asignación histórica.
                if not service.asignacion_snapshot:
                    raise error(409, 'renovacion_requiere_regularizacion', 'Regularizá la asignación del servicio antes de renovar')
                for field in ['template_id', 'definicion_version_id', 'vcpus', 'ram_mb', 'disk_gb']:
                    if assignment.get(field) != service.asignacion_snapshot.get(field):
                        raise error(422, 'renovacion_sin_cambio_recursos', 'La renovación conserva la asignación del servicio original')
                assignment = dict(service.asignacion_snapshot)
            pedido.revision_decision += 1
            pedido.template_id, pedido.definicion_version_id = template.id, definition.id if definition else None
            pedido.asignacion_snapshot, pedido.destino_snapshot = assignment, destination
            pedido.vigencia_tipo = VigenciaTipo(body.vigencia.tipo)
            pedido.anio_lectivo = body.vigencia.anio_lectivo
            pedido.vigencia_desde = period.inicio_at.replace(tzinfo=None)
            pedido.vigencia_hasta = period.fin_exclusivo_at.replace(tzinfo=None)
            pedido.decision_snapshot = {'revision_decision': pedido.revision_decision, 'asignacion': assignment,
                'destino': destination, 'vigencia': evaluation['vigencia_efectiva'], 'template_revision': template.revision}
            period_entry = VigenciaAutorizada(id=uuid4(), pedido_id=pedido.id, revision_decision=pedido.revision_decision,
                servicio_id=service.id if service else None, modalidad=body.vigencia.tipo, anio_lectivo=body.vigencia.anio_lectivo,
                calendario_id=period.calendario_id, calendario_revision=period.calendario_revision,
                desde_local=period.desde, hasta_local=period.hasta, zona_horaria=period.zona_horaria,
                inicio_at=period.inicio_at, fin_exclusivo_at=period.fin_exclusivo_at, aprobado_por=actor.id, aprobado_at=clock.now())
            if service:
                from app.services.renovacion_service import registrar_aprobacion
                await registrar_aprobacion(session, pedido, service, period_entry, actor=actor)
            session.add(period_entry)
            if pedido.tipo == TipoPedido.ALTA:
                expiry = expiracion_reserva(period, clock.now())
                commitment = CompromisoCapacidad(pedido_id=pedido.id, nodo=destination['nodo'], storage_id=destination['storage'],
                    storage_scope=destination['storage_scope'], vcpus_retenidos=assignment['vcpus'],
                    ram_mb_retenida=assignment['ram_mb'], disk_bytes_retenidos=assignment['disk_gb'] * 1024**3,
                    estado='reservado', creado_at=clock.now(), expira_at=expiry,
                    justificacion_sobreasignacion=body.justificacion_capacidad)
                session.add(commitment)
            pedido.justificacion_capacidad = body.justificacion_capacidad
            from app.services.pedido_service import transicionar
            await transicionar(session, pedido.id, EstadoPedido.APROBADO, usuario=actor,
                motivo='Asignación efectiva y vigencia aprobadas', evento_clave=f'decision:{pedido.revision_decision}:aprobada', metadata=pedido.decision_snapshot)
            if service:
                await transicionar(session, pedido.id, EstadoPedido.EN_DESPLIEGUE, usuario=actor,
                    motivo='Registro de condiciones de renovación', evento_clave=f'decision:{pedido.revision_decision}:registrando')
                await transicionar(session, pedido.id, EstadoPedido.ACTIVO, usuario=actor,
                    motivo='Renovación registrada; conserva estado e identidad del servicio', evento_clave=f'decision:{pedido.revision_decision}:registrada')
            if body.desplegar_inmediatamente:
                operation = await _queue_deploy(session, pedido, actor=actor, clave=clave, payload=normalized_payload)
                return ResultadoDecision(202, operation_response(operation))
            return ResultadoDecision(200, {'id': pedido.id, 'pedido_id': pedido.id, 'estado': pedido.estado.value,
                'revision_decision': pedido.revision_decision, 'asignacion_snapshot': assignment, 'destino_snapshot': destination,
                'vigencia_efectiva': evaluation['vigencia_efectiva'],
                'disponibilidad': 'esperando_inicio' if clock.now() < period.inicio_at else ('renovacion_registrada' if service else 'listo_para_desplegar')})

    return await ejecutar(db, actor_id=actor.id, clave=clave, metodo='POST', ruta=f'/pedidos/{pedido_id}/aprobar',
        payload=normalized_payload, decidir=decide, target_tipo='pedido', target_id=pedido_id)


async def desplegar(db, pedido_id, *, actor, clave):
    actor = await requiere_admin_actual(db, actor)
    await requiere_acceso_pedido(db, actor, pedido_id)
    async def decide(session):
        async with capacidad_service.bloqueo_capacidad(session):
            pedido = await _request(session, pedido_id)
            if pedido.tipo != TipoPedido.ALTA or pedido.estado != EstadoPedido.APROBADO:
                previous = await _open_operation(session, pedido)
                if previous:
                    raise error(409, 'operacion_en_curso', 'El pedido tiene una operación pendiente', operation_id=str(previous.id))
                if pedido.servicio_id and pedido.estado == EstadoPedido.EN_DESPLIEGUE:
                    existing = await session.get(Servicio, pedido.servicio_id)
                    if existing and not existing.deleted_at and existing.disponibilidad_aplicacion != 'utilizable':
                        raise error(409, 'verificacion_acceso_pendiente', 'El recurso ya existe; falta verificar el acceso')
                raise error(409, 'estado_incompatible', 'El pedido no tiene una alta aprobada pendiente de despliegue')
            commitment = await _ledger(session, pedido_id)
            period = await session.scalar(select(VigenciaAutorizada).where(VigenciaAutorizada.pedido_id == pedido_id,
                VigenciaAutorizada.revision_decision == pedido.revision_decision, VigenciaAutorizada.revocada_at.is_(None)))
            if not commitment or not period or not pedido.asignacion_snapshot or not pedido.destino_snapshot:
                raise error(409, 'asignacion_sin_regularizar', 'El pedido requiere una decisión de asignación y vigencia comprobada')
            if clock.now() < db_utc(period.inicio_at):
                raise error(409, 'inicio_futuro', 'El despliegue se habilita desde la fecha inicial aprobada')
            if clock.now() >= db_utc(period.fin_exclusivo_at):
                raise error(409, 'vigencia_vencida', 'La vigencia autorizada ya terminó')
            if commitment.expira_at and clock.now() >= db_utc(commitment.expira_at):
                raise error(409, 'reserva_caducada', 'La reserva venció; se requiere una nueva decisión')
            operation = await _queue_deploy(session, pedido, actor=actor, clave=clave, payload={})
            return ResultadoDecision(202, operation_response(operation))
    return await ejecutar(db, actor_id=actor.id, clave=clave, metodo='POST', ruta=f'/servicios/desplegar/{pedido_id}',
                         payload={}, decidir=decide, target_tipo='pedido', target_id=pedido_id)


async def iniciar(db, servicio_id, *, actor, clave, motivo=None, pve=None):
    actor = await usuario_actual(db, actor)
    await requiere_acceso_servicio(db, actor, servicio_id)
    async def decide(session):
        async with capacidad_service.bloqueo_capacidad(session):
            service = await session.scalar(select(Servicio).where(Servicio.id == servicio_id).with_for_update()
                .execution_options(populate_existing=True))
            await requiere_acceso_servicio(session, actor, servicio_id)
            if getattr(service.tipo, 'value', service.tipo) != 'lxc':
                raise error(422, 'tipo_no_soportado', 'Las nuevas operaciones requieren un recurso LXC regularizado')
            if service.estado not in {EstadoServicio.STOPPED, EstadoServicio.PAUSED}:
                raise error(409, 'estado_incompatible', 'Solo se inicia un servicio detenido o pausado confirmado')
            from sqlalchemy import or_
            previous = await session.scalar(select(OperacionInfraestructura).where(
                or_(OperacionInfraestructura.servicio_id == service.id,
                    OperacionInfraestructura.identidad_infraestructura_id == service.identidad_infraestructura_id),
                OperacionInfraestructura.estado.in_(OPEN)).with_for_update())
            if previous:
                raise error(409, 'operacion_en_curso', 'Ya existe una operación abierta', operation_id=str(previous.id))
            from app.services.vigencia_service import exigir_cobertura
            await exigir_cobertura(session, service.id, clock.now())
            ledger = await session.scalar(select(CompromisoCapacidad).where(CompromisoCapacidad.servicio_id == service.id,
                CompromisoCapacidad.liberado_at.is_(None)).with_for_update().execution_options(populate_existing=True))
            identity = await session.get(IdentidadInfraestructura, service.identidad_infraestructura_id) if service.identidad_infraestructura_id else None
            if not ledger or not identity or not service.asignacion_snapshot or not service.nombre_snapshot or not service.modelo_servicio:
                raise error(409, 'asignacion_sin_regularizar', 'Regularizá identidad y asignación antes de iniciar')
            if ledger.estado == 'incierto' or identity.estado == 'incierta':
                raise error(409, 'reconciliacion_pendiente', 'El estado anterior todavía requiere reconciliación')
            from app.services import inventario_service
            inventory = await inventario_service.leer(pve)
            resource = inventory['recursos'].get(identity.vmid)
            if not resource or not capacidad_service._owned(resource, identity, inventory['cluster_id']):
                raise error(409, 'identidad_no_verificada', 'La identidad de infraestructura debe reconciliarse antes de operar')
            snapshot = service.asignacion_snapshot
            if resource['configurado_vcpus'] != snapshot['vcpus'] or resource['configurado_ram_mb'] != snapshot['ram_mb']:
                raise error(409, 'asignacion_infra_cambiada', 'La configuración actual no coincide con la asignación autorizada')
            capacity = await capacidad_service.panorama(session, inventario=inventory,
                destino={'nodo': ledger.nodo, 'storage': ledger.storage_id})
            incremental = {'vcpus': max(0, snapshot['vcpus'] - max(ledger.vcpus_retenidos, resource['vcpus'])),
                'ram_mb': max(0, snapshot['ram_mb'] - max(ledger.ram_mb_retenida, resource['ram_mb']))}
            if any(amount > 0 and amount > capacity['libre'][field] for field, amount in incremental.items()):
                raise error(409, 'sin_capacidad', 'El servicio sigue pausado; no hay capacidad para reactivarlo ahora', reintentable=True)
            ledger.vcpus_retenidos, ledger.ram_mb_retenida = snapshot['vcpus'], snapshot['ram_mb']
            ledger.revision += 1
            operation = OperacionInfraestructura(tipo='iniciar', pedido_id=service.pedido_id, servicio_id=service.id,
                identidad_infraestructura_id=identity.id, actor_usuario_id=actor.id, actor_tipo='usuario', actor_id_normalizado=str(actor.id),
                idempotency_key=clave, request_hash=hashlib.sha256(safe_json({'motivo': motivo}).encode()).hexdigest(),
                motivo=motivo, estado='pendiente', fase='preparacion', creado_at=clock.now(), updated_at=clock.now(), next_poll_at=clock.now())
            operation.contexto_seguro = {'catedra_id': service.catedra_id, 'asignacion': snapshot,
                'destino': {'nodo': ledger.nodo, 'storage': ledger.storage_id, 'storage_scope': ledger.storage_scope}}
            session.add(operation)
            await session.flush()
            from app.services.historial_service import registrar_servicio
            session.add(registrar_servicio(service.id, service.estado.value, service.estado.value,
                comentario='Inicio admitido; todavía no confirmado', usuario=actor, operacion_id=operation.id,
                evento_clave=f'operacion:{operation.id}:admitida'))
            return ResultadoDecision(202, operation_response(operation))
    return await ejecutar(db, actor_id=actor.id, clave=clave, metodo='POST', ruta=f'/servicios/{servicio_id}/iniciar',
        payload={'motivo': motivo}, decidir=decide, target_tipo='servicio', target_id=servicio_id)


async def _liberar_pedido(db, pedido, *, actor, motivo, expirar=False, nuevo_estado=EstadoPedido.RECHAZADO, observaciones=None):
    """Requiere lock 4001 y fila de pedido; no hace commit ni I/O externo."""
    if pedido.estado not in {EstadoPedido.APROBADO, EstadoPedido.EN_DESPLIEGUE} or pedido.tipo != TipoPedido.ALTA:
        raise error(409, 'estado_incompatible', 'Solo puede liberarse una alta aprobada sin dispatch')
    ledger = await _ledger(db, pedido.id)
    if not ledger or (expirar and (not ledger.expira_at or db_utc(ledger.expira_at) > clock.now())):
        raise error(409, 'reserva_no_liberable', 'La reserva no corresponde a esa liberación')
    if ledger.estado != 'reservado':
        raise error(409, 'reconciliacion_pendiente', 'Un compromiso materializado o incierto solo se libera tras confirmar el efecto real')
    operation = await _open_operation(db, pedido)
    if pedido.estado == EstadoPedido.EN_DESPLIEGUE and operation is None:
        raise error(409, 'reconciliacion_pendiente', 'No se conoce el resultado del despliegue')
    if operation:
        if operation.fase != 'preparacion' or operation.upid or operation.estado == 'incierta':
            raise error(409, 'despliegue_en_curso', 'El envío iniciado o incierto debe reconciliarse antes de liberar', operation_id=str(operation.id))
        operation.estado, operation.fase, operation.error_codigo = 'fallida', 'cancelada', 'cancelada_antes_dispatch'
        operation.lease_owner, operation.lease_until = None, None
        operation.lease_generation += 1
    released = {'vcpus': ledger.vcpus_retenidos, 'ram_mb': ledger.ram_mb_retenida, 'storage_gb': ledger.disk_bytes_retenidos // 1024**3}
    ledger.vcpus_retenidos = ledger.ram_mb_retenida = ledger.disk_bytes_retenidos = 0
    ledger.estado, ledger.liberado_at, ledger.expira_at = 'liberado', clock.now(), None
    ledger.revision += 1
    period = await db.scalar(select(VigenciaAutorizada).where(VigenciaAutorizada.pedido_id == pedido.id,
        VigenciaAutorizada.revision_decision == pedido.revision_decision, VigenciaAutorizada.revocada_at.is_(None)))
    if period:
        period.revocada_at = clock.now()
    # Cantidades autorizadas/snapshots e historia anterior se conservan.
    pedido.motivo_rechazo = motivo if nuevo_estado == EstadoPedido.RECHAZADO else None
    if observaciones is not None:
        pedido.observaciones_ajuste = observaciones
    from app.services.pedido_service import transicionar
    await transicionar(db, pedido.id, nuevo_estado, usuario=actor, motivo=motivo,
        evento_clave=f'decision:{pedido.revision_decision}:liberada', metadata={'capacidad_liberada': released})
    return released


async def liberar(db, pedido_id, *, actor, motivo, expirar=False, clave=None, nuevo_estado=EstadoPedido.RECHAZADO, observaciones=None):
    if actor:
        actor = await requiere_admin_actual(db, actor)
        await requiere_acceso_pedido(db, actor, pedido_id)
    elif not expirar:
        raise error(403, 'sin_permisos', 'La decisión requiere un administrador actual')
    if not motivo or not motivo.strip():
        raise error(422, 'motivo_requerido', 'Indicá el motivo de la liberación')
    initial = await db.get(Pedido, pedido_id)
    revision = initial.revision_decision if initial else None
    async def decide(session):
        async with capacidad_service.bloqueo_capacidad(session):
            pedido = await _request(session, pedido_id)
            if revision != pedido.revision_decision:
                raise error(409, 'decision_desactualizada', 'La decisión autorizada cambió durante la liberación')
            released = await _liberar_pedido(session, pedido, actor=actor, motivo=motivo,
                expirar=expirar, nuevo_estado=nuevo_estado, observaciones=observaciones)
            return ResultadoDecision(200, {'id': pedido.id, 'pedido_id': pedido.id, 'estado': pedido.estado.value, 'capacidad_liberada': released})
    action = 'expirar-reserva' if expirar else ('solicitar-ajuste' if nuevo_estado == EstadoPedido.REQUIERE_AJUSTE else 'revertir-aprobacion')
    return await ejecutar(db, actor_id=actor.id if actor else 'expiracion_reservas', actor_tipo='usuario' if actor else 'sistema',
        clave=clave or f'expirar:{pedido_id}:{revision}', metodo='POST', ruta=f'/pedidos/{pedido_id}/{action}',
        payload={'motivo': motivo, 'expirar': expirar, 'estado': nuevo_estado.value, 'observaciones': observaciones},
        decidir=decide, target_tipo='pedido', target_id=pedido_id)


async def ajustar(db, pedido_id, *, actor, observaciones, clave):
    actor = await requiere_admin_actual(db, actor)
    await requiere_acceso_pedido(db, actor, pedido_id)
    if not observaciones or not observaciones.strip():
        raise error(422, 'observaciones_requeridas', 'Indicá las correcciones necesarias')
    async def decide(session):
        async with capacidad_service.bloqueo_capacidad(session):
            pedido = await _request(session, pedido_id)
            released = {'vcpus': 0, 'ram_mb': 0, 'storage_gb': 0}
            reason = 'Ajuste solicitado por administración: ' + observaciones
            if pedido.estado in {EstadoPedido.APROBADO, EstadoPedido.EN_DESPLIEGUE}:
                released = await _liberar_pedido(session, pedido, actor=actor, motivo=reason,
                    nuevo_estado=EstadoPedido.REQUIERE_AJUSTE, observaciones=observaciones)
            elif pedido.estado == EstadoPedido.SOLICITADO:
                if await _open_operation(session, pedido):
                    raise error(409, 'operacion_en_curso', 'El pedido tiene una operación abierta')
                pedido.observaciones_ajuste = observaciones
                from app.services.pedido_service import transicionar
                await transicionar(session, pedido.id, EstadoPedido.REQUIERE_AJUSTE, usuario=actor,
                    motivo=reason, evento_clave=f'ajuste:{clave}')
            else:
                raise error(409, 'estado_incompatible', 'El pedido no admite ajustes en su estado actual')
            return ResultadoDecision(200, {'id': pedido.id, 'pedido_id': pedido.id, 'estado': pedido.estado.value,
                'observaciones_ajuste': observaciones, 'capacidad_liberada': released})
    return await ejecutar(db, actor_id=actor.id, clave=clave, metodo='POST', ruta=f'/pedidos/{pedido_id}/solicitar-ajuste',
        payload={'observaciones': observaciones}, decidir=decide, target_tipo='pedido', target_id=pedido_id)


async def dar_de_baja(db, pedido_id, *, actor, clave):
    actor = await requiere_admin_actual(db, actor)
    initial = await db.get(Pedido, pedido_id)
    if initial is None:
        raise error(404, 'pedido_no_encontrado', 'Pedido no encontrado')
    from app.services.acceso_service import requiere_acceso_catedra
    await requiere_acceso_catedra(db, actor, initial.catedra_id)
    async def decide(session):
        async with capacidad_service.bloqueo_capacidad(session):
            pedido = await session.scalar(select(Pedido).where(Pedido.id == pedido_id).with_for_update()
                .execution_options(populate_existing=True))
            if pedido.deleted_at:
                return ResultadoDecision(200, {'pedido_id': pedido.id, 'deleted_at': evaluacion_service.utc_z(pedido.deleted_at)})
            alive = await session.scalar(select(Servicio.id).where(Servicio.pedido_id == pedido_id, Servicio.deleted_at.is_(None)))
            if alive:
                raise error(409, 'servicio_vigente', 'Dá de baja primero el recurso para confirmar su ausencia')
            ledger = await _ledger(session, pedido_id)
            released = {'vcpus': 0, 'ram_mb': 0, 'storage_gb': 0}
            if ledger:
                released = await _liberar_pedido(session, pedido, actor=actor, motivo='Baja administrativa antes de dispatch')
            elif await _open_operation(session, pedido):
                raise error(409, 'operacion_en_curso', 'Resolver la operación abierta antes de retirar el pedido')
            pedido.deleted_at = clock.now().replace(tzinfo=None)
            from app.services.historial_service import registrar_pedido
            session.add(registrar_pedido(pedido.id, pedido.estado.value, pedido.estado.value,
                comentario='Baja lógica administrativa; se conserva historia', usuario=actor, evento_clave='baja_logica'))
            return ResultadoDecision(200, {'pedido_id': pedido.id, 'deleted_at': evaluacion_service.utc_z(pedido.deleted_at), 'capacidad_liberada': released})
    return await ejecutar(db, actor_id=actor.id, clave=clave, metodo='DELETE', ruta=f'/pedidos/{pedido_id}',
                         payload={}, decidir=decide, target_tipo='pedido', target_id=pedido_id)
