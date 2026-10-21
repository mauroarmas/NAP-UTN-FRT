"""Solicitudes locales idempotentes; fechas completas y transiciones únicas."""
import hashlib
from sqlalchemy import select

from app.config import get_settings
from app.models.catedra import Catedra
from app.models.pedido import Pedido, EstadoPedido, ModeloServicio, VigenciaTipo, TipoPedido
from app.models.recurso_template import RecursoTemplate, TipoRecurso
from app.schemas.pedido import PedidoCreate, PedidoResponse, PedidoReenviar
from app.services import vigencia_service, historial_service, capacidad_service
from app.services.acceso_service import usuario_actual, catedras_visibles, requiere_admin_actual, requiere_acceso_pedido
from app.services.idempotencia_service import ejecutar, ResultadoDecision
from app.utils.clock import clock
from app.utils.errors import error


async def validar(db, data, *, historical=False):
    query = select(RecursoTemplate).where(RecursoTemplate.id == data.template_id)
    if not historical:
        query = query.with_for_update()
    template = await db.scalar(query.execution_options(populate_existing=True))
    if (not template or (not historical and (not template.activo or template.tipo != TipoRecurso.LXC
        or template.modelo_servicio.value != data.modelo_servicio))):
        raise error(422, 'plantilla_incompatible', 'Elegí una plantilla LXC vigente del modelo solicitado')
    if not historical:
        from app.services.perfiles_service import exigir_definicion
        await exigir_definicion(db, template, bloquear=True)
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
            estado=EstadoPedido.SOLICITADO, tipo=TipoPedido.ALTA,
            created_at=clock.now().replace(tzinfo=None), updated_at=clock.now().replace(tzinfo=None))
        request.definicion_version_id = (await session.get(RecursoTemplate, data.template_id)).definicion_version_id
        asignar_vigencia(request, data.vigencia, period)
        session.add(request)
        await session.flush()
        session.add(historial_service.registrar_pedido(request.id, 'nuevo', request.estado.value,
            comentario='Solicitud creada con vigencia explícita', usuario=actor))
        return ResultadoDecision(201, await presentar(session, request))
    return await ejecutar(db, actor_id=actor.id, clave=clave, metodo='POST', ruta='/pedidos/',
        payload=data.model_dump(mode='json', exclude_none=True), decidir=decide, target_tipo='catedra', target_id=category_id)


async def resolver(db, pedido_id, *, actor, tipo, payload, clave):
    actor = await requiere_admin_actual(db, actor)
    await requiere_acceso_pedido(db, actor, pedido_id)
    if tipo not in {'reenviar', 'cancelar', 'rechazar'}:
        raise ValueError('Acción de solicitud no permitida')
    normalized = payload.model_dump(mode='json', exclude_none=True) if hasattr(payload, 'model_dump') else payload
    async def decide(session):
        async with capacidad_service.bloqueo_capacidad(session):
            request = await session.scalar(select(Pedido).where(Pedido.id == pedido_id).with_for_update()
                .execution_options(populate_existing=True))
            if not request or request.deleted_at:
                raise error(404, 'pedido_no_encontrado', 'Pedido no encontrado')
            allowed = {EstadoPedido.REQUIERE_AJUSTE} if tipo == 'reenviar' else {EstadoPedido.SOLICITADO, EstadoPedido.REQUIERE_AJUSTE}
            if request.estado not in allowed:
                raise error(409, 'estado_incompatible', 'La solicitud no admite esta acción')
            from app.services.pedido_service import transicionar
            if tipo == 'reenviar':
                data = PedidoReenviar.model_validate(normalized)
                effective = PedidoCreate(template_id=data.template_id or request.template_id,
                    modelo_servicio=data.modelo_servicio or request.modelo_servicio.value,
                    descripcion_requerimientos=data.descripcion_requerimientos,
                    vigencia=data.vigencia, catedra_id=request.catedra_id)
                if request.tipo == TipoPedido.RENOVACION and (effective.template_id != request.template_id
                    or effective.modelo_servicio != request.modelo_servicio.value):
                    raise error(422, 'renovacion_sin_cambio_recursos', 'La renovación conserva el producto y asignación')
                period = await validar(session, effective, historical=request.tipo == TipoPedido.RENOVACION)
                request.template_id, request.modelo_servicio = effective.template_id, ModeloServicio(effective.modelo_servicio)
                if request.tipo == TipoPedido.ALTA:
                    request.definicion_version_id = (await session.get(RecursoTemplate, effective.template_id)).definicion_version_id
                if data.descripcion_requerimientos is not None:
                    request.descripcion_requerimientos = data.descripcion_requerimientos
                asignar_vigencia(request, data.vigencia, period)
                request.observaciones_ajuste = None
                state, reason = EstadoPedido.SOLICITADO, 'Solicitud corregida y reenviada por administración'
            else:
                reason = normalized.get('motivo', '').strip()
                if not reason:
                    raise error(422, 'motivo_requerido', 'Indicá el motivo')
                state = EstadoPedido.CANCELADO if tipo == 'cancelar' else EstadoPedido.RECHAZADO
                if state == EstadoPedido.RECHAZADO:
                    request.motivo_rechazo = reason
            event_key = 'solicitud:' + hashlib.sha256(f'{actor.id}:{clave}'.encode()).hexdigest()
            await transicionar(session, request.id, state, usuario=actor, motivo=reason, evento_clave=event_key)
            return ResultadoDecision(200, await presentar(session, request))
    return await ejecutar(db, actor_id=actor.id, clave=clave, metodo='POST', ruta=f'/pedidos/{pedido_id}/{tipo}',
        payload=normalized, decidir=decide, target_tipo='pedido', target_id=pedido_id)
