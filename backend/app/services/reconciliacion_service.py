"""Reconciliación: observar un envío incierto nunca autoriza a repetirlo."""
import hashlib
from sqlalchemy import select, or_

from app.models.operacion_infraestructura import OperacionInfraestructura
from app.models.pedido import Pedido, EstadoPedido
from app.models.identidad_infraestructura import IdentidadInfraestructura
from app.models.compromiso_capacidad import CompromisoCapacidad
from app.services import identidad_infra_service as identities, operacion_service, capacidad_service
from app.services.infraestructura_io import consultar, InfraNoVerificable
from app.services.acceso_service import requiere_admin_actual, requiere_acceso_pedido
from app.services.idempotencia_service import ejecutar, ResultadoDecision, safe_json
from app.utils.clock import clock, db_utc
from app.utils.errors import error

TASK_TYPES = {'crear': 'vzcreate', 'iniciar': 'vzstart', 'detener': 'vzstop', 'reiniciar': 'vzreboot', 'eliminar': 'vzdestroy'}


async def recuperar_upid(operation, identity, *, pve=None):
    if identity is None or operation.dispatch_started_at is None:
        return None
    action = operation.contexto_seguro.get('accion_externa')
    if action not in TASK_TYPES:
        return None
    observation = await identities.observar(identity, pve=pve)
    if observation.estado != 'propia' and not (action == 'eliminar' and observation.estado == 'ausente'):
        return None
    since = int(db_utc(operation.dispatch_started_at).timestamp())
    tasks = await consultar('get_node_tasks', identity.nodo, vmid=identity.vmid,
        since=since, tipo=TASK_TYPES[action], pve=pve)
    if tasks.estado != 'presente' or not isinstance(tasks.valor, list):
        raise InfraNoVerificable()
    matches = [row for row in tasks.valor if row.get('type') == TASK_TYPES[action]
        and str(row.get('id')) == str(identity.vmid) and row.get('node') == identity.nodo
        and isinstance(row.get('starttime'), (int, float)) and row['starttime'] >= since
        and isinstance(row.get('upid'), str) and row['upid'].startswith('UPID:') and len(row['upid']) <= 300]
    # Más de una candidata, falta de permisos o historia purgada no acreditan
    # una tarea. El recurso por sí solo tampoco confirma el resultado externo.
    return matches[0]['upid'] if len(matches) == 1 else None


async def reintentar(db, pedido_id, *, actor, clave, motivo=None, pve=None):
    actor = await requiere_admin_actual(db, actor)
    await requiere_acceso_pedido(db, actor, pedido_id)
    async def decide(session):
        async with capacidad_service.bloqueo_capacidad(session):
            request = await session.scalar(select(Pedido).where(Pedido.id == pedido_id).with_for_update())
            if not request or request.deleted_at:
                raise error(404, 'pedido_no_encontrado', 'Pedido no encontrado')
            if request.estado != EstadoPedido.ERROR:
                raise error(409, 'estado_incompatible', 'Solo se reintenta una operación fallida revisada')
            if request.configuracion_despliegue_id:
                from app.services.application_compatibility_service import require_document
                require_document(request.asignacion_snapshot['configuracion'])
            previous = await session.scalar(select(OperacionInfraestructura).where(OperacionInfraestructura.pedido_id == pedido_id)
                .order_by(OperacionInfraestructura.creado_at.desc(), OperacionInfraestructura.id.desc()).limit(1))
            if not previous:
                raise error(409, 'requiere_nueva_decision', 'Regularizá el pedido antes de reintentar')
            identity = await session.get(IdentidadInfraestructura, previous.identidad_infraestructura_id) if previous.identidad_infraestructura_id else None
            active = await session.scalar(select(OperacionInfraestructura).where(OperacionInfraestructura.estado.in_(operacion_service.OPEN),
                or_(OperacionInfraestructura.pedido_id == pedido_id,
                    OperacionInfraestructura.identidad_infraestructura_id == identity.id if identity else OperacionInfraestructura.pedido_id == pedido_id)))
            if active:
                raise error(409, 'operacion_en_curso', 'El resultado anterior debe reconciliarse', operation_id=str(active.id))
            ledger = await session.scalar(select(CompromisoCapacidad).where(CompromisoCapacidad.pedido_id == pedido_id,
                CompromisoCapacidad.liberado_at.is_(None)).with_for_update())
            if not identity or identity.ausencia_confirmada_at or not ledger:
                raise error(409, 'requiere_nueva_decision', 'La reserva anterior no habilita otra creación')
            observation = await identities.observar(identity, pve=pve)
            if observation.estado != 'propia':
                raise error(409, 'reconciliacion_pendiente', 'La identidad debe reconciliarse antes de reintentar')
            if observation.status != 'running':
                raise error(409, 'requiere_inicio', 'El recurso detenido requiere admisión de capacidad antes de reparar')
            operation = OperacionInfraestructura(tipo='reparar', pedido_id=pedido_id, servicio_id=previous.servicio_id,
                identidad_infraestructura_id=identity.id, actor_usuario_id=actor.id, actor_tipo='usuario',
                actor_id_normalizado=str(actor.id), idempotency_key=clave,
                request_hash=hashlib.sha256(safe_json({'motivo': motivo}).encode()).hexdigest(), motivo=motivo,
                estado='pendiente', fase='preparacion', contexto_seguro={**previous.contexto_seguro, 'accion_externa': 'bootstrap'},
                next_poll_at=clock.now(), creado_at=clock.now(), updated_at=clock.now())
            session.add(operation)
            await session.flush()
            from app.services.pedido_service import transicionar
            await transicionar(session, pedido_id, EstadoPedido.EN_DESPLIEGUE, usuario=actor,
                motivo='Reparación admitida sobre la identidad existente', operacion_id=operation.id,
                evento_clave=f'operacion:{operation.id}:admitida')
            from app.services.admision_service import operation_response
            return ResultadoDecision(202, operation_response(operation))
    return await ejecutar(db, actor_id=actor.id, clave=clave, metodo='POST', ruta=f'/pedidos/{pedido_id}/reintentar',
        payload={'motivo': motivo}, decidir=decide, target_tipo='pedido', target_id=pedido_id)


async def reconciliar_operaciones(db):
    import asyncio
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.worker import procesar_una
    sessions = async_sessionmaker(db.bind, expire_on_commit=False)
    await db.commit()
    results = await asyncio.gather(*(procesar_una(sessions) for _ in range(4)))
    return {'afectados': sum(results), 'detalle': 'Resultados conservados o confirmados mediante el ejecutor durable'}
