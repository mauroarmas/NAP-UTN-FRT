"""Evaluación de selección efectiva, firmada y revalidada al admitir."""
from dataclasses import asdict
import base64
import hashlib
import hmac
import json

from pydantic import ValidationError
from sqlalchemy import select

from app.config import get_settings
from app.models.pedido import Pedido, EstadoPedido, TipoPedido
from app.models.recurso_template import RecursoTemplate, TipoRecurso
from app.models.definicion_servicio import DefinicionServicio
from app.schemas.asignacion import SeleccionEvaluacion
from app.services.acceso_service import requiere_admin_actual, requiere_acceso_pedido
from app.services import capacidad_service, inventario_service, vigencia_service
from app.utils.clock import clock, db_utc
from app.utils.errors import error


def _typed(payload):
    try:
        return payload if isinstance(payload, SeleccionEvaluacion) else SeleccionEvaluacion.model_validate(payload)
    except ValidationError:
        raise error(422, 'datos_invalidos', 'Revisá asignación, destino y vigencia de la evaluación') from None


def utc_z(instant):
    return db_utc(instant).isoformat().replace('+00:00', 'Z')


def _b64(raw):
    return base64.urlsafe_b64encode(raw).decode().rstrip('=')


def _sign(raw):
    return hmac.new(get_settings().secret_key.encode(), b'nap:evaluation:v1:' + raw, hashlib.sha256).digest()


def token_for(fingerprint, actor_id, pedido_id):
    now = int(clock.now().timestamp())
    data = {'v': 1, 'actor': actor_id, 'pedido': pedido_id, 'huella': fingerprint, 'iat': now, 'exp': now + 60}
    raw = json.dumps(data, sort_keys=True, separators=(',', ':')).encode()
    return _b64(raw) + '.' + _b64(_sign(raw))


def verificar_token(token, *, huella, actor_id, pedido_id):
    try:
        if not isinstance(token, str) or len(token) > 4096:
            raise ValueError()
        body, signature = token.split('.')
        raw = base64.b64decode(body + '=' * (-len(body) % 4), altchars=b'-_', validate=True)
        supplied = base64.b64decode(signature + '=' * (-len(signature) % 4), altchars=b'-_', validate=True)
        if not hmac.compare_digest(supplied, _sign(raw)):
            raise ValueError()
        data = json.loads(raw)
        if set(data) != {'v', 'actor', 'pedido', 'huella', 'iat', 'exp'} or data['v'] != 1:
            raise ValueError()
        if (data['actor'], data['pedido'], data['huella']) != (actor_id, pedido_id, huella):
            raise ValueError()
        if any(type(data[key]) is not int for key in ['actor', 'pedido', 'iat', 'exp']):
            raise ValueError()
        if not data['iat'] <= clock.now().timestamp() < data['exp'] or data['exp'] - data['iat'] != 60:
            raise ValueError()
    except (ValueError, TypeError, KeyError, UnicodeError):
        raise error(409, 'evaluacion_desactualizada', 'La selección o capacidad cambió: evaluá y confirmá nuevamente', reintentable=True) from None


async def calcular(db, pedido_id, *, actor, payload, pve=None, bloquear=False):
    actor = await requiere_admin_actual(db, actor)
    await requiere_acceso_pedido(db, actor, pedido_id)
    selection = _typed(payload)
    pedido = await db.scalar(select(Pedido).where(Pedido.id == pedido_id).execution_options(populate_existing=True))
    if pedido is None or pedido.deleted_at:
        raise error(404, 'pedido_no_encontrado', 'Pedido no encontrado')
    if pedido.estado != EstadoPedido.SOLICITADO:
        raise error(409, 'estado_incompatible', 'Solo se evalúan solicitudes pendientes de decisión')
    if pedido.tipo == TipoPedido.RENOVACION:
        from app.services.renovacion_service import calcular as evaluar_renovacion
        return await evaluar_renovacion(db, pedido, selection)
    template_query = select(RecursoTemplate).where(RecursoTemplate.id == selection.asignacion.template_id)
    if bloquear:
        template_query = template_query.with_for_update()
    template = await db.scalar(template_query.execution_options(populate_existing=True))
    if not template or not template.activo or template.tipo != TipoRecurso.LXC or template.modelo_servicio != pedido.modelo_servicio:
        raise error(422, 'plantilla_incompatible', 'Elegí una plantilla LXC vigente del modelo solicitado')
    from app.models.definicion_servicio import DefinicionServicio
    offered_definition=await db.get(DefinicionServicio,template.definicion_version_id) if template.definicion_version_id else None
    library=bool(offered_definition and offered_definition.incorporacion_id)
    if not selection.asignacion.definicion_version_id or selection.asignacion.definicion_version_id != template.definicion_version_id:
        if library:
            raise error(409, 'evaluacion_desactualizada', 'La oferta cambió; actualizá el catálogo y volvé a evaluar', definicion_version_id=str(template.definicion_version_id), version=offered_definition.version)
        raise error(422, 'definicion_incompatible', 'La evaluación debe usar la definición vinculada al perfil seleccionado')
    from app.services.perfiles_service import exigir_definicion
    definition = await exigir_definicion(db, template, bloquear=bloquear)
    minimums = definition.manifest['minimum_resources']
    image = definition.manifest['image']['volume_id']
    assignment = selection.asignacion.model_dump(mode='json')
    if any(assignment[key] < minimums[key] for key in minimums):
        raise error(422, 'recursos_inferiores_minimos', 'La asignación no alcanza los mínimos validados del producto')
    period = await vigencia_service.resolver_solicitud(db, selection.vigencia.model_dump(mode='json', exclude_none=True), get_settings().institutional_timezone)
    if period.fin_exclusivo_at <= clock.now():
        raise error(422, 'vigencia_finalizada', 'La fecha final ya pasó')
    inventory = await inventario_service.leer(pve)
    overview = await capacidad_service.panorama(db, inventario=inventory)
    cost = {key: assignment[key] if pedido.tipo == TipoPedido.ALTA else 0 for key in ['vcpus', 'ram_mb', 'disk_gb']}
    if selection.destino is None:
        adequate = [entry for entry in overview['destinos'] if all(entry['libre'][key] >= cost[key] for key in cost)]
        destination = (adequate or overview['destinos'])[0]['destino']
    else:
        destination = selection.destino.model_dump(mode='json')
    capacity = next((entry for entry in overview['destinos'] if entry['destino'] == destination), None)
    if capacity is None:
        raise error(422, 'destino_no_permitido', 'Elegí un destino LXC elegible del inventario autorizado')
    if not image or not isinstance(image, str) or not __import__('re').fullmatch(r'[A-Za-z][A-Za-z0-9_-]*:vztmpl/[A-Za-z0-9][A-Za-z0-9_.-]*\.tar\.(zst|xz|gz)', image):
        raise error(422, 'imagen_no_preparada', 'La plantilla necesita una imagen LXC preparada')
    image_storage = image.split(':', 1)[0]
    from app.services.infraestructura_io import consultar
    try:
        observed = await consultar('get_available_templates', destination['nodo'], image_storage, pve=pve)
        images = observed.valor if observed.estado == 'presente' else []
        if not any(entry.get('volid') == image and entry.get('content') == 'vztmpl' for entry in images):
            raise error(422, 'imagen_no_disponible', 'La imagen preparada no está disponible en el nodo elegido')
    except Exception as exc:
        if getattr(exc, 'status_code', None) == 422:
            raise
        raise error(502, 'imagen_no_verificable', 'No se pudo verificar la imagen de despliegue') from None
    normalized = selection.model_dump(mode='json', exclude_none=True)
    normalized['destino'] = destination
    dates = {key: value.isoformat() if hasattr(value, 'isoformat') else value for key, value in asdict(period).items()}
    dates['inicio_at'], dates['fin_exclusivo_at'] = utc_z(period.inicio_at), utc_z(period.fin_exclusivo_at)
    exceeds = any(capacity['libre'][key] < cost[key] for key in cost)
    constraints = []
    if cost['disk_gb'] * 1024**3 > capacity['storage_fisico_libre_bytes']:
        constraints.append('espacio_fisico_insuficiente')
    if cost['vcpus'] > capacity['fisica']['vcpus']:
        constraints.append('vcpus_superan_nodo')
    if cost['ram_mb'] > capacity['fisica']['ram_mb']:
        constraints.append('ram_supera_nodo')
    state = {'pedido_revision': pedido.revision, 'template_revision': template.revision,
             'template': {key: getattr(template, key) for key in ['nombre', 'os_template', 'default_vcpus', 'default_ram_mb', 'default_disk_gb', 'config_extra']},
             'definicion_hash': inventario_service.fingerprint(definition.manifest) if definition else None,
             'seleccion': normalized, 'vigencia': dates, 'inventario_compromisos': overview['capacidad_token']}
    fingerprint = inventario_service.fingerprint(state)
    result = {'pedido_id': pedido.id, 'seleccion': normalized, 'vigencia_efectiva': dates,
        'costo_incremental': cost, 'libre_antes': {key: capacity['libre'][key] for key in cost},
        'libre_despues': {key: capacity['libre'][key] - cost[key] for key in cost},
        'storage_scope': capacity['storage_scope'], 'excede_capacidad': exceeds, 'justificacion_requerida': exceeds,
        'restricciones_fisicas': constraints, 'limites': capacity, 'observado_at': utc_z(clock.now())}
    if library:
        original=pedido.seleccion_oferta_snapshot or {}
        result.update(version_solicitada=original.get('version'), version_efectiva=definition.version,
            cambio_version=bool(original.get('definicion_id') and original['definicion_id']!=str(definition.id)))
    return result, fingerprint, pedido, template, definition, period, image


async def evaluar(db, pedido_id, *, actor, payload, pve=None):
    result, fingerprint, *_ = await calcular(db, pedido_id, actor=actor, payload=payload, pve=pve)
    return {**result, 'capacidad_token': token_for(fingerprint, actor.id, pedido_id)}
