"""Renovar registra cobertura; no crea recursos ni garantiza cómputo futuro."""
from dataclasses import asdict
from uuid import UUID

from sqlalchemy import select

from app.config import get_settings
from app.models.pedido import Pedido, EstadoPedido, TipoPedido, ModeloServicio
from app.models.servicio import Servicio
from app.models.recurso_template import RecursoTemplate
from app.models.definicion_servicio import DefinicionServicio
from app.models.compromiso_capacidad import CompromisoCapacidad
from app.models.vigencia import VigenciaAutorizada
from app.services import capacidad_service, vigencia_service, inventario_service, historial_service
from app.services.acceso_service import requiere_acceso_servicio, requiere_admin_actual, usuario_actual
from app.services.idempotencia_service import ejecutar, ResultadoDecision
from app.utils.clock import clock, db_utc
from app.utils.errors import error


async def validar_periodo(db, service, period, *, sustituye_id=None):
    current = await vigencia_service.periodos_vigentes(db, service.id)
    if not current:
        raise error(409, 'vigencia_sin_regularizar', 'El servicio requiere períodos históricos comprobados')
    target = next((entry for entry in current if entry.id == sustituye_id), None) if sustituye_id else None
    if sustituye_id and target is None:
        raise error(409, 'vigencia_desactualizada', 'El período ya fue sustituido o no pertenece al servicio')
    for previous in current:
        if previous.id == sustituye_id:
            continue
        if max(db_utc(previous.inicio_at), period.inicio_at) < min(db_utc(previous.fin_exclusivo_at), period.fin_exclusivo_at):
            raise error(422, 'vigencia_solapada', 'El período se solapa con otra vigencia autorizada')
    return current


async def solicitar(db, servicio_id, *, actor, body, clave, sustituye_id=None):
    actor = await (requiere_admin_actual(db, actor) if sustituye_id else usuario_actual(db, actor))
    await requiere_acceso_servicio(db, actor, servicio_id)
    if sustituye_id and body.sustituye_vigencia_id != sustituye_id:
        raise error(422, 'vigencia_incompatible', 'El período del cuerpo debe coincidir con el de la ruta')
    if sustituye_id and not body.motivo.strip():
        raise error(422, 'motivo_requerido', 'Indicá el motivo de la modificación')
    normalized = body.model_dump(mode='json', exclude_none=True)
    async def decide(session):
        async with capacidad_service.bloqueo_capacidad(session):
            service = await session.scalar(select(Servicio).where(Servicio.id == servicio_id).with_for_update()
                .execution_options(populate_existing=True))
            await requiere_acceso_servicio(session, actor, servicio_id)
            ledger = await session.scalar(select(CompromisoCapacidad).where(CompromisoCapacidad.servicio_id == service.id,
                CompromisoCapacidad.liberado_at.is_(None)))
            if (not service.asignacion_snapshot or not ledger or service.tipo != 'lxc'
                or not service.modelo_servicio or not service.identidad_infraestructura_id):
                raise error(409, 'asignacion_sin_regularizar', 'Regularizá la asignación antes de renovar')
            period = await vigencia_service.resolver_solicitud(session, normalized['vigencia'], get_settings().institutional_timezone)
            if period.fin_exclusivo_at <= clock.now():
                raise error(422, 'vigencia_finalizada', 'La fecha final ya pasó')
            await validar_periodo(session, service, period, sustituye_id=sustituye_id)
            candidates = list((await session.scalars(select(Pedido).where(Pedido.servicio_id == service.id,
                Pedido.tipo == TipoPedido.RENOVACION, Pedido.deleted_at.is_(None),
                Pedido.estado.in_([EstadoPedido.SOLICITADO, EstadoPedido.REQUIERE_AJUSTE, EstadoPedido.APROBADO, EstadoPedido.EN_DESPLIEGUE])))).all())
            if any(entry.sustituye_vigencia_id == sustituye_id and entry.vigencia_desde and entry.vigencia_hasta
                and db_utc(entry.vigencia_desde) == period.inicio_at and db_utc(entry.vigencia_hasta) == period.fin_exclusivo_at for entry in candidates):
                raise error(409, 'renovacion_pendiente', 'Ya existe una solicitud equivalente pendiente')
            request = Pedido(catedra_id=service.catedra_id, solicitante_id=actor.id, template_id=service.template_id,
                modelo_servicio=ModeloServicio(service.modelo_servicio), tipo=TipoPedido.RENOVACION,
                servicio_id=service.id, estado=EstadoPedido.SOLICITADO, sustituye_vigencia_id=sustituye_id,
                descripcion_requerimientos=normalized.get('motivo'), asignacion_snapshot=service.asignacion_snapshot,
                definicion_version_id=service.definicion_version_id,
                configuracion_despliegue_id=service.configuracion_despliegue_id,
                destino_snapshot={'nodo': ledger.nodo, 'storage': ledger.storage_id, 'storage_scope': ledger.storage_scope},
                created_at=clock.now().replace(tzinfo=None), updated_at=clock.now().replace(tzinfo=None))
            from app.services.solicitud_service import asignar_vigencia
            asignar_vigencia(request, body.vigencia, period)
            session.add(request)
            await session.flush()
            session.add(historial_service.registrar_pedido(request.id, 'nuevo', request.estado.value,
                comentario='Modificación de período solicitada' if sustituye_id else 'Renovación solicitada; cobertura pendiente de aprobación',
                usuario=actor, metadata={'servicio_id': service.id, 'sustituye_vigencia_id': str(sustituye_id) if sustituye_id else None}))
            return ResultadoDecision(201, {'pedido_id': request.id, 'id': request.id, 'servicio_id': service.id,
                'tipo': 'renovacion', 'estado': request.estado.value,
                'sustituye_vigencia_id': str(sustituye_id) if sustituye_id else None, 'vigencia': normalized['vigencia']})
    route = f'/servicios/{servicio_id}/renovar' if not sustituye_id else f'/servicios/{servicio_id}/vigencias/{sustituye_id}/modificaciones'
    return await ejecutar(db, actor_id=actor.id, clave=clave, metodo='POST', ruta=route,
        payload=normalized, decidir=decide, target_tipo='servicio', target_id=servicio_id)


async def calcular(db, request, selection):
    service = await db.get(Servicio, request.servicio_id, populate_existing=True)
    if not service or service.deleted_at or service.catedra_id != request.catedra_id or not service.asignacion_snapshot:
        raise error(409, 'servicio_renovacion_invalido', 'El servicio original ya no admite esa renovación')
    ledger = await db.scalar(select(CompromisoCapacidad).where(CompromisoCapacidad.servicio_id == service.id,
        CompromisoCapacidad.liberado_at.is_(None)))
    if not ledger or service.tipo != 'lxc':
        raise error(409, 'asignacion_sin_regularizar', 'La asignación requiere regularización')
    expected = service.asignacion_snapshot
    selected = selection.asignacion.model_dump(mode='json')
    for field in ['template_id', 'definicion_version_id', 'configuracion_despliegue_id', 'vcpus', 'ram_mb', 'disk_gb']:
        if selected.get(field) != expected.get(field):
            raise error(422, 'renovacion_sin_cambio_recursos', 'La renovación conserva producto, recursos y contenedor')
    destination = {'nodo': ledger.nodo, 'storage': ledger.storage_id}
    if selection.destino and selection.destino.model_dump() != destination:
        raise error(422, 'renovacion_sin_cambio_destino', 'La renovación conserva el destino existente')
    period = await vigencia_service.resolver_solicitud(db, selection.vigencia.model_dump(mode='json', exclude_none=True),
        get_settings().institutional_timezone)
    if period.fin_exclusivo_at <= clock.now():
        raise error(422, 'vigencia_finalizada', 'La fecha final ya pasó')
    current = await validar_periodo(db, service, period, sustituye_id=request.sustituye_vigencia_id)
    template = await db.get(RecursoTemplate, service.template_id)
    if template is None:
        raise error(409, 'asignacion_sin_regularizar', 'Falta la referencia histórica de la plantilla')
    definition = await db.get(DefinicionServicio, service.definicion_version_id) if service.definicion_version_id else None
    dates = {key: value.isoformat() if hasattr(value, 'isoformat') else value for key, value in asdict(period).items()}
    normalized = selection.model_dump(mode='json', exclude_none=True)
    normalized['destino'] = destination
    state = {'pedido_revision': request.revision, 'servicio_id': service.id, 'identidad': str(service.identidad_infraestructura_id),
        'asignacion': expected, 'catedra_id': service.catedra_id, 'estado': service.estado.value,
        'sustituye': str(request.sustituye_vigencia_id), 'motivo': request.descripcion_requerimientos,
        'periodos': [{'id': str(entry.id), 'inicio': db_utc(entry.inicio_at).isoformat(),
            'fin': db_utc(entry.fin_exclusivo_at).isoformat()} for entry in current],
        'seleccion': normalized, 'vigencia': dates, 'storage_scope': ledger.storage_scope}
    zero = {'vcpus': 0, 'ram_mb': 0, 'disk_gb': 0}
    unknown = dict.fromkeys(zero)
    result = {'pedido_id': request.id, 'seleccion': normalized, 'vigencia_efectiva': dates,
        'costo_incremental': zero, 'libre_antes': unknown, 'libre_despues': unknown,
        'storage_scope': ledger.storage_scope, 'excede_capacidad': False, 'justificacion_requerida': False,
        'restricciones_fisicas': [], 'limites': None, 'observado_at': None,
        'mensaje': 'Registrar condiciones no reserva cómputo ni enciende el servicio'}
    return result, inventario_service.fingerprint(state), request, template, definition, period, expected.get('image', {}).get('volume_id')


async def registrar_aprobacion(db, request, service, period_entry, *, actor):
    resolved = vigencia_service.VigenciaResuelta(period_entry.desde_local, period_entry.hasta_local, period_entry.zona_horaria,
        db_utc(period_entry.inicio_at), db_utc(period_entry.fin_exclusivo_at))
    # El servicio y lock 4001 ya están tomados por la admisión. La comprobación
    # vuelve a excluir la vigencia objetivo justo antes de sustituirla.
    await validar_periodo(db, service, resolved, sustituye_id=request.sustituye_vigencia_id)
    period_entry.sustituye_id = request.sustituye_vigencia_id
    service.vence_at = max([db_utc(entry.fin_exclusivo_at) for entry in await vigencia_service.periodos_vigentes(db, service.id)]
        + [db_utc(period_entry.fin_exclusivo_at)]).replace(tzinfo=None)
    db.add(historial_service.registrar_servicio(service.id, service.estado.value, service.estado.value,
        comentario='Condiciones de renovación registradas; el estado del contenedor se conserva', usuario=actor,
        evento_clave=f'renovacion:{request.id}:{request.revision_decision}',
        metadata={'pedido_id': request.id, 'vigencia_id': str(period_entry.id),
            'sustituye_id': str(request.sustituye_vigencia_id) if request.sustituye_vigencia_id else None}))
