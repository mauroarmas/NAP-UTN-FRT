from dataclasses import dataclass
from datetime import timedelta
import json
from uuid import UUID

from sqlalchemy import select, update, or_

from app.models.operacion_infraestructura import OperacionInfraestructura
from app.models.pedido import Pedido
from app.models.servicio import Servicio
from app.models.usuario import RolUsuario
from app.models.compromiso_capacidad import CompromisoCapacidad
from app.models.identidad_infraestructura import IdentidadInfraestructura
from app.models.servicio import EstadoServicio
from app.services.acceso_service import usuario_actual, catedras_visibles
from app.services.idempotencia_service import safe_json
from app.utils.clock import clock, db_utc
from app.utils.errors import error

OPEN = ['pendiente', 'en_curso', 'incierta']


@dataclass(frozen=True)
class LeaseOperacion:
    id: UUID
    owner: UUID
    generation: int


async def reclamar(db, *, owner, lease_seconds=30):
    if not isinstance(owner, UUID) or not 5 <= lease_seconds <= 120:
        raise ValueError('Lease inválido')
    operation = await db.scalar(select(OperacionInfraestructura).where(
        OperacionInfraestructura.estado.in_(OPEN), OperacionInfraestructura.next_poll_at <= clock.now(),
        or_(OperacionInfraestructura.lease_owner.is_(None), OperacionInfraestructura.lease_until <= clock.now()))
        .order_by(OperacionInfraestructura.next_poll_at, OperacionInfraestructura.creado_at, OperacionInfraestructura.id)
        .with_for_update(skip_locked=True).limit(1).execution_options(populate_existing=True))
    if operation is None:
        return None
    operation.lease_owner = owner
    operation.lease_until = clock.now() + timedelta(seconds=lease_seconds)
    operation.lease_generation += 1
    operation.intento += 1
    operation.estado, operation.updated_at = 'en_curso', clock.now()
    await db.flush()
    return LeaseOperacion(operation.id, owner, operation.lease_generation)


def condicion_lease(lease):
    return (OperacionInfraestructura.id == lease.id, OperacionInfraestructura.lease_owner == lease.owner,
        OperacionInfraestructura.lease_generation == lease.generation, OperacionInfraestructura.lease_until > clock.now(),
        OperacionInfraestructura.estado.in_(OPEN))


async def actualizar(db, lease, **values):
    allowed = {'estado', 'fase', 'upid', 'error_codigo', 'error_detalle_seguro', 'confirmada_at', 'next_poll_at',
               'lease_owner', 'lease_until', 'contexto_seguro', 'dispatch_started_at', 'deadline_at',
               'pedido_id', 'servicio_id', 'identidad_infraestructura_id'}
    if set(values) - allowed:
        raise ValueError('Campo de operación no actualizable')
    if 'contexto_seguro' in values:
        values['contexto_seguro'] = json.loads(safe_json(values['contexto_seguro']))
    if 'estado' in values and values['estado'] not in [*OPEN, 'confirmada', 'fallida']:
        raise ValueError('Estado de operación inválido')
    values['updated_at'] = clock.now()
    result = await db.execute(update(OperacionInfraestructura).where(*condicion_lease(lease))
        .values(**values).execution_options(synchronize_session=False))
    return result.rowcount == 1


async def heartbeat(db, lease, *, lease_seconds=30):
    if not 5 <= lease_seconds <= 120:
        raise ValueError('Duración de lease inválida')
    return await actualizar(db, lease, lease_until=clock.now() + timedelta(seconds=lease_seconds))


async def terminar(db, lease, *, estado, error_codigo=None, error_detalle_seguro=None, **extra):
    if estado not in {'confirmada', 'fallida'}:
        raise ValueError('La terminación requiere un resultado final')
    return await actualizar(db, lease, estado=estado, lease_owner=None, lease_until=None,
        confirmada_at=clock.now() if estado == 'confirmada' else None,
        error_codigo=error_codigo, error_detalle_seguro=error_detalle_seguro, **extra)


async def ceder(db, lease, *, incierta=False, segundos=2, error_codigo=None, error_detalle_seguro=None):
    return await actualizar(db, lease, estado='incierta' if incierta else 'en_curso',
        lease_owner=None, lease_until=None, next_poll_at=clock.now() + timedelta(seconds=segundos),
        error_codigo=error_codigo, error_detalle_seguro=error_detalle_seguro)


async def obtener(db, identity, *, usuario):
    usuario = await usuario_actual(db, usuario)
    entry = await db.get(OperacionInfraestructura, identity, populate_existing=True)
    if entry is None:
        raise error(404, 'operacion_no_encontrada', 'Operación no encontrada')
    category = None
    if entry.servicio_id:
        service = await db.get(Servicio, entry.servicio_id)
        category = service.catedra_id if service else None
    elif entry.pedido_id:
        request = await db.get(Pedido, entry.pedido_id)
        category = request.catedra_id if request else None
    if category is None:
        if usuario.rol != RolUsuario.ADMIN:
            raise error(403, 'sin_permisos', 'No tenés acceso a esta operación')
    elif category not in await catedras_visibles(db, usuario):
        raise error(403, 'sin_permisos', 'No tenés acceso a esta operación')
    return entry


async def listar(db, *, usuario, pedido_id=None, servicio_id=None, abiertas=False, limit=50, cursor=None):
    import base64
    from sqlalchemy import case
    from app.services.acceso_service import requiere_acceso_catedra
    usuario = await usuario_actual(db, usuario)
    for model, value in [(Pedido, pedido_id), (Servicio, servicio_id)]:
        if value is not None:
            entity = await db.get(model, value)
            if entity is None:
                raise error(404, 'recurso_no_encontrado', 'Recurso no encontrado')
            await requiere_acceso_catedra(db, usuario, entity.catedra_id)
    query = select(OperacionInfraestructura).outerjoin(Servicio,
        Servicio.id == OperacionInfraestructura.servicio_id).outerjoin(Pedido,
        Pedido.id == OperacionInfraestructura.pedido_id)
    if usuario.rol != RolUsuario.ADMIN:
        query = query.where(case((Servicio.id.is_not(None), Servicio.catedra_id), else_=Pedido.catedra_id)
            .in_(await catedras_visibles(db, usuario)))
    if pedido_id is not None:
        query = query.where(OperacionInfraestructura.pedido_id == pedido_id)
    if servicio_id is not None:
        query = query.where(OperacionInfraestructura.servicio_id == servicio_id)
    if abiertas:
        query = query.where(OperacionInfraestructura.estado.in_(OPEN))
    if cursor:
        try:
            boundary = UUID(base64.urlsafe_b64decode(cursor + '=' * (-len(cursor) % 4)).decode('ascii'))
        except (ValueError, UnicodeError):
            raise error(422, 'cursor_invalido', 'Cursor de operaciones inválido') from None
        query = query.where(OperacionInfraestructura.id > boundary)
    entries = list((await db.scalars(query.order_by(OperacionInfraestructura.id).limit(limit + 1))).all())
    more = len(entries) > limit
    entries = entries[:limit]
    return {'items': [presentar(entry) for entry in entries],
        'next_cursor': base64.urlsafe_b64encode(str(entries[-1].id).encode()).decode().rstrip('=') if more else None}


async def anexar_operaciones(db, servicios):
    if not servicios:
        return servicios
    entries = list((await db.scalars(select(OperacionInfraestructura).where(
        OperacionInfraestructura.servicio_id.in_([service.id for service in servicios]),
        OperacionInfraestructura.estado.in_(OPEN)))).all())
    active = {entry.servicio_id: entry.id for entry in entries}
    from sqlalchemy import func
    confirmations = dict((await db.execute(select(OperacionInfraestructura.servicio_id,
        func.max(OperacionInfraestructura.confirmada_at)).where(OperacionInfraestructura.servicio_id.in_([service.id for service in servicios]),
        OperacionInfraestructura.estado == 'confirmada').group_by(OperacionInfraestructura.servicio_id))).all())
    for service in servicios:
        service.operation_id = active.get(service.id)
        service.confirmado_at = confirmations.get(service.id)
    return servicios


async def anexar_pedidos(db, pedidos):
    if not pedidos:
        return pedidos
    entries = list((await db.execute(select(OperacionInfraestructura.pedido_id, OperacionInfraestructura.id).where(
        OperacionInfraestructura.pedido_id.in_([p.id for p in pedidos]), OperacionInfraestructura.estado.in_(OPEN)))).all())
    active = dict(entries)
    from app.models.vigencia import VigenciaAutorizada
    periods = list((await db.scalars(select(VigenciaAutorizada).where(
        VigenciaAutorizada.pedido_id.in_([p.id for p in pedidos]),
        VigenciaAutorizada.revocada_at.is_(None)))).all())
    by_revision = {(p.pedido_id, p.revision_decision): p for p in periods}
    ledgers = {row.pedido_id:row for row in (await db.scalars(select(CompromisoCapacidad).where(
        CompromisoCapacidad.pedido_id.in_([p.id for p in pedidos]),CompromisoCapacidad.liberado_at.is_(None)))).all()}
    for request in pedidos:
        request.operation_id = active.get(request.id)
        period = by_revision.get((request.id, request.revision_decision))
        ledger = ledgers.get(request.id)
        request.compromiso_capacidad = ({key:getattr(ledger,key) for key in
            ['estado','vcpus_retenidos','ram_mb_retenida','disk_bytes_retenidos','expira_at']} if ledger else None)
        if ledger and ledger.expira_at: request.compromiso_capacidad['expira_at']=db_utc(ledger.expira_at)
        request.vigencia_aprobada = ({'desde': period.desde_local.isoformat(), 'hasta': period.hasta_local.isoformat(),
            'zona_horaria': period.zona_horaria, 'inicio_at': db_utc(period.inicio_at).isoformat(),
            'fin_exclusivo_at': db_utc(period.fin_exclusivo_at).isoformat(),
            'calendario_revision': period.calendario_revision} if period else None)
        request.despliegue_habilitado = bool(request.estado.value == 'aprobado' and request.tipo.value == 'alta'
            and not request.operation_id and not request.servicio_id and period
            and db_utc(period.inicio_at) <= clock.now() < db_utc(period.fin_exclusivo_at)
            and ledger and ledger.estado == 'reservado' and ledger.expira_at and clock.now() < db_utc(ledger.expira_at))
    return pedidos


def presentar(entry):
    fields = ['tipo', 'estado', 'fase', 'pedido_id', 'servicio_id', 'intento', 'error_codigo',
              'error_detalle_seguro', 'creado_at', 'updated_at', 'confirmada_at', 'next_poll_at']
    result = {'operation_id': str(entry.id)}
    if entry.contexto_seguro.get('sin_cambios'):
        result['sin_cambios'] = True
    for key in fields:
        value = getattr(entry, key)
        result[key] = db_utc(value).isoformat().replace('+00:00', 'Z') if value is not None and key.endswith('_at') else value
    return result


async def admitir_orden(db, servicio_id, *, tipo, usuario=None, clave, motivo=None, sistema=None):
    """Acciones sin nueva asignación; el efecto siempre lo confirma el worker."""
    from app.services.acceso_service import requiere_acceso_catedra, requiere_admin_actual
    from app.services import capacidad_service
    from app.services.idempotencia_service import ejecutar, ResultadoDecision
    import hashlib
    if tipo not in {'detener', 'reiniciar', 'pausar', 'eliminar', 'reparar'}:
        raise ValueError('Acción no admitida')
    if usuario is None:
        if sistema not in {'vencimiento', 'inactividad', 'reconciliacion'} or tipo not in {'pausar', 'detener'}:
            raise ValueError('Actor de sistema no autorizado')
    else:
        usuario = await (requiere_admin_actual(db, usuario) if tipo in {'eliminar', 'reparar'} else usuario_actual(db, usuario))
    initial = await db.get(Servicio, servicio_id)
    if initial is None:
        raise error(404, 'servicio_no_encontrado', 'Servicio no encontrado')
    if usuario:
        await requiere_acceso_catedra(db, usuario, initial.catedra_id)
    actor_id = usuario.id if usuario else sistema
    async def decide(session):
        async with capacidad_service.bloqueo_capacidad(session):
            service = await session.scalar(select(Servicio).where(Servicio.id == servicio_id).with_for_update()
                .execution_options(populate_existing=True))
            if service.deleted_at:
                if tipo == 'eliminar':
                    return ResultadoDecision(200, {'servicio_id': service.id, 'estado': 'retirado', 'sin_cambios': True})
                raise error(409, 'servicio_retirado', 'El servicio ya fue retirado')
            if getattr(service.tipo, 'value', service.tipo) != 'lxc':
                raise error(422, 'tipo_no_soportado', 'La operación requiere un recurso LXC regularizado')
            if usuario:
                await requiere_acceso_catedra(session, usuario, service.catedra_id)
            previous = await session.scalar(select(OperacionInfraestructura).where(
                or_(OperacionInfraestructura.servicio_id == service.id,
                    OperacionInfraestructura.identidad_infraestructura_id == service.identidad_infraestructura_id),
                OperacionInfraestructura.estado.in_(OPEN)).with_for_update())
            if previous:
                raise error(409, 'operacion_en_curso', 'Ya existe una operación abierta', operation_id=str(previous.id))
            identity = await session.get(IdentidadInfraestructura, service.identidad_infraestructura_id) if service.identidad_infraestructura_id else None
            ledger = await session.scalar(select(CompromisoCapacidad).where(CompromisoCapacidad.servicio_id == service.id,
                CompromisoCapacidad.liberado_at.is_(None)).with_for_update())
            if not identity or identity.ausencia_confirmada_at or not ledger or not service.asignacion_snapshot:
                raise error(409, 'asignacion_sin_regularizar', 'Regularizá identidad y asignación antes de operar')
            if sistema == 'vencimiento':
                from app.services.vigencia_service import periodos_vigentes, resumir_cobertura
                coverage = resumir_cobertura(await periodos_vigentes(session, service.id), clock.now())
                if coverage['estado'] == 'sin_regularizar':
                    raise error(409, 'vigencia_sin_regularizar', 'La cobertura requiere regularización')
                if coverage['cubierto']:
                    return ResultadoDecision(200, {'servicio_id': service.id, 'sin_cambios': True, 'motivo': 'cobertura_actualizada'})
            if tipo == 'reiniciar':
                if not service.nombre_snapshot or not service.modelo_servicio:
                    raise error(409, 'asignacion_sin_regularizar', 'Regularizá la asignación histórica antes de reiniciar')
                if ledger.estado == 'incierto' or identity.estado == 'incierta':
                    raise error(409, 'reconciliacion_pendiente', 'El estado anterior todavía requiere reconciliación')
                from app.services.vigencia_service import exigir_cobertura
                await exigir_cobertura(session, service.id, clock.now())
                if service.estado != EstadoServicio.RUNNING:
                    raise error(409, 'requiere_inicio', 'El servicio detenido debe iniciarse con control de capacidad')
            operation = OperacionInfraestructura(tipo=tipo, servicio_id=service.id, pedido_id=service.pedido_id,
                identidad_infraestructura_id=identity.id, actor_usuario_id=usuario.id if usuario else None,
                actor_tipo='usuario' if usuario else 'sistema', actor_id_normalizado=str(actor_id),
                idempotency_key=clave, request_hash=hashlib.sha256(safe_json({'motivo': motivo}).encode()).hexdigest(),
                motivo=motivo, estado='pendiente', fase='preparacion', creado_at=clock.now(), updated_at=clock.now(), next_poll_at=clock.now(),
                contexto_seguro={'catedra_id': service.catedra_id, 'asignacion': service.asignacion_snapshot,
                    'destino': {'nodo': ledger.nodo, 'storage': ledger.storage_id, 'storage_scope': ledger.storage_scope}})
            session.add(operation)
            await session.flush()
            from app.services.historial_service import registrar_servicio
            session.add(registrar_servicio(service.id, service.estado.value, service.estado.value,
                comentario='Orden admitida: ' + tipo + '; resultado pendiente', usuario=usuario,
                operacion_id=operation.id, evento_clave=f'operacion:{operation.id}:admitida'))
            from app.services.admision_service import operation_response
            return ResultadoDecision(202, operation_response(operation))
    return await ejecutar(db, actor_id=actor_id, actor_tipo='usuario' if usuario else 'sistema', clave=clave,
        metodo='DELETE' if tipo == 'eliminar' else 'POST', ruta=f'/servicios/{servicio_id}/{tipo}',
        payload={'motivo': motivo}, decidir=decide, target_tipo='servicio', target_id=servicio_id)
