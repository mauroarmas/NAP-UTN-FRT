"""Solicitudes locales idempotentes; fechas completas y transiciones únicas."""
import hashlib
from pydantic import ValidationError
from sqlalchemy import select

from app.config import get_settings
from app.models.catedra import Catedra
from app.models.pedido import Pedido, EstadoPedido, ModeloServicio, VigenciaTipo, TipoPedido
from app.models.recurso_template import RecursoTemplate, TipoRecurso
from app.schemas.pedido import PedidoCreate, PedidoResponse, PedidoReenviar
from app.services import vigencia_service, historial_service, capacidad_service, notificacion_service
from app.services.acceso_service import usuario_actual, catedras_visibles, requiere_admin_actual, requiere_acceso_pedido
from app.services.idempotencia_service import ejecutar, ResultadoDecision
from app.utils.clock import clock
from app.utils.errors import error


async def validar(db, data, *, historical=False):
    # «Otro» registra una necesidad; todavía no asigna ni reserva un recurso.
    if data.template_id is not None:
        query = select(RecursoTemplate).where(RecursoTemplate.id == data.template_id)
        if not historical:
            query = query.with_for_update()
        template = await db.scalar(query.execution_options(populate_existing=True))
        if (not template or (not historical and (not template.activo or template.tipo != TipoRecurso.LXC
            or template.modelo_servicio.value != data.modelo_servicio))):
            raise error(422, 'plantilla_incompatible', 'Elegí una plantilla LXC vigente del modelo solicitado')
        if not historical:
            from app.services.perfiles_service import exigir_definicion
            definition = await exigir_definicion(db, template, bloquear=True)
            if template.configuracion_despliegue_id and data.oferta_revision is not None and data.oferta_revision!=template.revision:
                raise error(409,'oferta_actualizada','La oferta cambió; revisá la aplicación antes de enviar',oferta_revision=template.revision)
            if definition and definition.incorporacion_id and data.oferta_revision is not None and data.oferta_revision != template.revision:
                raise error(409, 'oferta_actualizada', 'La oferta cambió; revisá la versión vigente antes de enviar', oferta_revision=template.revision, version=definition.version)
    elif historical:
        raise error(422, 'plantilla_requerida', 'La renovación requiere el recurso asignado originalmente')
    period = await vigencia_service.resolver_solicitud(db, data.vigencia.model_dump(mode='json', exclude_none=True),
        get_settings().institutional_timezone)
    if period.fin_exclusivo_at <= clock.now():
        raise error(422, 'vigencia_finalizada', 'La fecha final ya pasó')
    return period


def asignar_vigencia(request, data, period):
    request.vigencia_solicitada = data.model_dump(mode='json', exclude_none=True)
    request.vigencia_tipo = VigenciaTipo(data.tipo)
    request.anio_lectivo = data.anio_lectivo
    request.vigencia_desde = period.inicio_at.replace(tzinfo=None)
    request.vigencia_hasta = period.fin_exclusivo_at.replace(tzinfo=None)


async def presentar(db, request):
    category = await db.get(Catedra, request.catedra_id)
    data = {column.name: getattr(request, column.name) for column in Pedido.__table__.columns}
    data['catedra'] = {'id': category.id, 'nombre': category.nombre} if category else None
    response = PedidoResponse.model_validate(data).model_dump(mode='json')
    response['vigencia'] = request.vigencia_solicitada
    response['pedido_id'] = request.id
    return response


async def crear(db, *, actor, payload, clave):
    actor = await usuario_actual(db, actor)
    data = payload if isinstance(payload, PedidoCreate) else PedidoCreate.model_validate(payload)
    visible = await catedras_visibles(db, actor)
    category_id = data.catedra_id
    if category_id is None:
        if len(visible) != 1:
            raise error(422, 'catedra_requerida', 'Elegí la cátedra de la solicitud')
        category_id = next(iter(visible))
    if category_id not in visible:
        raise error(403, 'sin_permisos', 'No tenés acceso a esa cátedra')
    async def decide(session):
        # La autorización actual precede al replay; validaciones del catálogo
        # solo corresponden a una intención todavía no confirmada.
        if category_id not in await catedras_visibles(session, actor):
            raise error(403, 'sin_permisos', 'La cátedra ya no está disponible')
        period = await validar(session, data)
        request = Pedido(catedra_id=category_id, solicitante_id=actor.id, template_id=data.template_id,
            modelo_servicio=ModeloServicio(data.modelo_servicio), descripcion_requerimientos=data.descripcion_requerimientos,
            parametros_extra=data.parametros_extra.model_dump(exclude_none=True) if data.parametros_extra else None,
            estado=EstadoPedido.SOLICITADO, tipo=TipoPedido.ALTA,
            created_at=clock.now().replace(tzinfo=None), updated_at=clock.now().replace(tzinfo=None))
        if data.template_id is not None:
            selected=await session.get(RecursoTemplate,data.template_id)
            request.definicion_version_id=selected.definicion_version_id
            request.configuracion_despliegue_id=selected.configuracion_despliegue_id
        request.seleccion_oferta_snapshot = await snapshot_oferta(session, data.template_id)
        asignar_vigencia(request, data.vigencia, period)
        session.add(request)
        await session.flush()
        session.add(historial_service.registrar_pedido(request.id, 'nuevo', request.estado.value,
            comentario='Solicitud creada con vigencia explícita', usuario=actor))
        category = await session.get(Catedra, category_id)
        cat_nombre = category.nombre if category else f'#{category_id}'
        await notificacion_service.encolar_aviso_pedido(session, request,
            evento=f'pedido:{request.id}:creado', tipo='pedido_creado',
            asunto=f'[Nuevo Pedido Solicitado] Cátedra {cat_nombre} (#{request.id})',
            texto=f'Nuevo pedido #{request.id} solicitado para la cátedra {cat_nombre} ({request.modelo_servicio.value.upper()}).',
            destinatarios='admin')
        return ResultadoDecision(201, await presentar(session, request))
    return await ejecutar(db, actor_id=actor.id, clave=clave, metodo='POST', ruta='/pedidos/',
        payload=data.model_dump(mode='json', exclude_none=True), decidir=decide, target_tipo='catedra', target_id=category_id)


async def resolver(db, pedido_id, *, actor, tipo, payload, clave):
    actor = await (usuario_actual(db, actor) if tipo == 'reenviar' else requiere_admin_actual(db, actor))
    await requiere_acceso_pedido(db, actor, pedido_id)
    if tipo not in {'reenviar', 'cancelar', 'rechazar'}:
        raise ValueError('Acción de solicitud no permitida')
    normalized = payload.model_dump(mode='json', exclude_unset=True) if hasattr(payload, 'model_dump') else payload
    async def decide(session):
        async with capacidad_service.bloqueo_capacidad(session):
            await requiere_acceso_pedido(session, actor, pedido_id)
            request = await session.scalar(select(Pedido).where(Pedido.id == pedido_id).with_for_update()
                .execution_options(populate_existing=True))
            if not request or request.deleted_at:
                raise error(404, 'pedido_no_encontrado', 'Pedido no encontrado')
            allowed = {EstadoPedido.REQUIERE_AJUSTE} if tipo == 'reenviar' else {EstadoPedido.SOLICITADO, EstadoPedido.REQUIERE_AJUSTE}
            if tipo == 'rechazar' and request.estado == EstadoPedido.ERROR:
                from app.models.operacion_infraestructura import OperacionInfraestructura
                from app.models.identidad_infraestructura import IdentidadInfraestructura
                from app.models.compromiso_capacidad import CompromisoCapacidad
                from app.models.servicio import Servicio
                previous = await session.scalar(select(OperacionInfraestructura).where(
                    OperacionInfraestructura.pedido_id == request.id)
                    .order_by(OperacionInfraestructura.creado_at.desc(), OperacionInfraestructura.id.desc()).limit(1))
                identity = await session.get(IdentidadInfraestructura, previous.identidad_infraestructura_id) if previous and previous.identidad_infraestructura_id else None
                held = await session.scalar(select(CompromisoCapacidad.id).where(
                    CompromisoCapacidad.pedido_id == request.id, CompromisoCapacidad.liberado_at.is_(None)))
                alive = await session.scalar(select(Servicio.id).where(Servicio.pedido_id == request.id, Servicio.deleted_at.is_(None)))
                opened = await session.scalar(select(OperacionInfraestructura.id).where(
                    OperacionInfraestructura.pedido_id == request.id,
                    OperacionInfraestructura.estado.in_(['pendiente', 'en_curso', 'incierta'])))
                safe = previous and previous.estado == 'fallida' and (
                    identity and identity.ausencia_confirmada_at or
                    previous.identidad_infraestructura_id is None and previous.dispatch_started_at is None)
                if held or alive or opened or not safe:
                    raise error(409, 'reconciliacion_pendiente', 'Confirmá ausencia y liberación antes de cerrar el pedido fallido')
                allowed.add(EstadoPedido.ERROR)
            if request.estado not in allowed:
                raise error(409, 'estado_incompatible', 'La solicitud no admite esta acción')
            from app.services.pedido_service import transicionar
            if tipo == 'reenviar':
                data = PedidoReenviar.model_validate(normalized)
                try:
                    effective = PedidoCreate(oferta_revision=data.oferta_revision, template_id=data.template_id if 'template_id' in data.model_fields_set else request.template_id,
                        modelo_servicio=data.modelo_servicio or request.modelo_servicio.value,
                        descripcion_requerimientos=data.descripcion_requerimientos if data.descripcion_requerimientos is not None else request.descripcion_requerimientos,
                        parametros_extra=data.parametros_extra or {key: value for key, value in (request.parametros_extra or {}).items()
                            if key in {'titulo', 'software_solicitado', 'referencia_imagen', 'instrucciones_uso'}},
                        vigencia=data.vigencia, catedra_id=request.catedra_id)
                except ValidationError:
                    raise error(422, 'solicitud_incompleta', 'Revisá el servicio solicitado y su justificación pedagógica; infraestructura requiere plantilla') from None
                if request.tipo == TipoPedido.RENOVACION and (effective.template_id != request.template_id
                    or effective.modelo_servicio != request.modelo_servicio.value):
                    raise error(422, 'renovacion_sin_cambio_recursos', 'La renovación conserva el producto y asignación')
                period = await validar(session, effective, historical=request.tipo == TipoPedido.RENOVACION)
                request.template_id, request.modelo_servicio = effective.template_id, ModeloServicio(effective.modelo_servicio)
                if request.tipo == TipoPedido.ALTA:
                    selected=await session.get(RecursoTemplate,effective.template_id) if effective.template_id is not None else None
                    request.definicion_version_id=selected.definicion_version_id if selected else None
                    request.configuracion_despliegue_id=selected.configuracion_despliegue_id if selected else None
                if data.parametros_extra is not None:
                    request.parametros_extra = data.parametros_extra.model_dump(exclude_none=True)
                if data.descripcion_requerimientos is not None:
                    request.descripcion_requerimientos = data.descripcion_requerimientos
                if request.tipo == TipoPedido.ALTA:
                    request.seleccion_oferta_snapshot = await snapshot_oferta(session, effective.template_id)
                asignar_vigencia(request, data.vigencia, period)
                request.observaciones_ajuste = None
                state, reason = EstadoPedido.SOLICITADO, ('Solicitud corregida y reenviada por administración'
                    if actor.rol.value == 'admin' else 'Aclaración respondida y solicitud reenviada por la cátedra')
            else:
                reason = normalized.get('motivo', '').strip()
                if not reason:
                    raise error(422, 'motivo_requerido', 'Indicá el motivo')
                state = EstadoPedido.CANCELADO if tipo == 'cancelar' else EstadoPedido.RECHAZADO
                if state == EstadoPedido.RECHAZADO:
                    request.motivo_rechazo = reason
            event_key = 'solicitud:' + hashlib.sha256(f'{actor.id}:{clave}'.encode()).hexdigest()
            await transicionar(session, request.id, state, usuario=actor, motivo=reason, evento_clave=event_key)
            category = await session.get(Catedra, request.catedra_id)
            cat_nombre = category.nombre if category else f'#{request.catedra_id}'
            if tipo == 'reenviar':
                await notificacion_service.encolar_aviso_pedido(session, request,
                    evento=f'pedido:{request.id}:reenviado:{request.revision}', tipo='pedido_reenviado',
                    asunto=f'[Pedido Reenviado para Revisión] Cátedra {cat_nombre} (#{request.id})',
                    texto=f'El pedido #{request.id} de la cátedra {cat_nombre} fue corregido y reenviado para revisión. Justificación: {request.descripcion_requerimientos or "Sin descripción adicional"}',
                    destinatarios='admin')
            elif state == EstadoPedido.RECHAZADO:
                await notificacion_service.encolar_aviso_pedido(session, request,
                    evento=f'pedido:{request.id}:rechazado:{request.revision}', tipo='pedido_rechazado',
                    asunto=f'[Pedido Rechazado] Pedido #{request.id} - Cátedra {cat_nombre}',
                    texto=f'Tu pedido #{request.id} para la cátedra {cat_nombre} fue rechazado. Motivo: {reason}',
                    destinatarios='titular')
            return ResultadoDecision(200, await presentar(session, request))
    return await ejecutar(db, actor_id=actor.id, clave=clave, metodo='POST', ruta=f'/pedidos/{pedido_id}/{tipo}',
        payload=normalized, decidir=decide, target_tipo='pedido', target_id=pedido_id)


async def snapshot_oferta(db,template_id):
    if template_id is None: return None
    from app.models.definicion_servicio import DefinicionServicio
    template=await db.get(RecursoTemplate,template_id)
    if template and template.configuracion_despliegue_id:
        from app.models.configuracion_despliegue import ConfiguracionDespliegue
        row=await db.get(ConfiguracionDespliegue,template.configuracion_despliegue_id)
        return {'template_id':template.id,'revision':template.revision,'nombre':template.nombre,
            'configuracion_id':str(row.id),'configuracion_revision':row.revision,'configuracion_sha256':row.sha256} if row else None
    definition=await db.get(DefinicionServicio,template.definicion_version_id) if template and template.definicion_version_id else None
    if not definition or definition.incorporacion_id is None: return None
    return {'template_id':template.id,'revision':template.revision,'definicion_id':str(definition.id),
        'version':definition.version,'nombre':template.nombre}
