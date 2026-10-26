"""Acceso inicial separado: autorización antes de cualquier descifrado."""
from uuid import UUID

from sqlalchemy import select

from app.models.definicion_servicio import DefinicionServicio
from app.models.evento_seguridad import EventoSeguridad
from app.models.identidad_infraestructura import IdentidadInfraestructura
from app.models.operacion_infraestructura import OperacionInfraestructura
from app.models.servicio import Servicio, EstadoServicio
from app.models.usuario import RolUsuario
from app.services.acceso_service import requiere_acceso_servicio, usuario_actual
from app.services.vigencia_service import periodos_vigentes, resumir_cobertura
from app.utils.clock import clock
from app.utils.errors import error
from app.utils.secretos import configured_keyring, SecretError


async def preparacion_confirmada(db, service):
    metadata = service.acceso_metadata or {}
    try:
        reference = UUID(metadata['preparacion_id'])
    except (ValueError, KeyError, TypeError):
        return None
    latest = await db.scalar(select(OperacionInfraestructura).where(
        OperacionInfraestructura.servicio_id == service.id,
        OperacionInfraestructura.tipo.in_(['desplegar', 'reparar']))
        .order_by(OperacionInfraestructura.creado_at.desc(), OperacionInfraestructura.id.desc()).limit(1))
    if (not latest or latest.id != reference or latest.estado != 'confirmada' or not latest.confirmada_at
        or latest.identidad_infraestructura_id != service.identidad_infraestructura_id or metadata.get('local_health') is not True):
        return None
    return latest


async def _context(db, actor, service_id):
    service = await requiere_acceso_servicio(db, actor, service_id)
    actor = await usuario_actual(db, actor)
    definition = await db.get(DefinicionServicio, service.definicion_version_id) if service.definicion_version_id else None
    metadata = service.acceso_metadata or {}
    product = definition.producto if definition else None
    method = {'linux': 'consola', 'postgresql': 'postgresql', 'bookstack': 'https', 'drawio': 'https'}.get(product)
    preparation = await preparacion_confirmada(db, service)
    covered = resumir_cobertura(await periodos_vigentes(db, service.id), clock.now())['cubierto']
    prepared = bool(preparation and product and metadata.get('metodo') == method and metadata.get('endpoint') and service.credenciales_encrypted)
    running = service.estado == EstadoServicio.RUNNING
    deliverable = service.disponibilidad_aplicacion == 'utilizable' and service.evidencia_acceso_id is not None
    may_reveal = bool(prepared and running and covered and (actor.rol == RolUsuario.ADMIN or deliverable))
    if not prepared:
        state, instructions = 'no_preparado', 'La preparación inicial todavía no está confirmada.'
    elif not running or not covered:
        state = 'no_disponible'
        instructions = 'Los datos se conservan. Iniciá el servicio con vigencia autorizada antes de usar el acceso.'
    elif deliverable:
        state = 'entregado'
        instructions = ('Acceso inicial entregado. Si cambiaste la contraseña en la aplicación, usá la nueva. '
            'Gestioná las cuentas individuales de lectura dentro de BookStack.' if product == 'bookstack' else
            'Acceso inicial entregado. Si cambiaste la contraseña en el servicio, usá la nueva.')
    else:
        state = 'solo_validacion' if actor.rol == RolUsuario.ADMIN else 'pendiente_verificacion'
        instructions = 'Falta comprobar acceso desde la red prevista. Administración puede revelar el acceso inicial solo para esa validación.'
    if product == 'drawio' and deliverable:
        instructions = 'Acceso HTTPS de esta instancia. Guardá los diagramas como archivos editables en tu equipo; NAP no ofrece guardado centralizado ni cuentas de Draw.io.'
    result = {'servicio_id': service.id, 'modelo_servicio': service.modelo_servicio, 'producto': product,
        'disponibilidad': service.disponibilidad_aplicacion, 'verificado_at': service.acceso_red_verificado_at,
        'metodo': method, 'direccion': metadata.get('endpoint'), 'puerto': metadata.get('port'),
        'puede_revelar_credenciales': may_reveal, 'estado_entrega': state, 'instrucciones': instructions}
    if actor.rol == RolUsuario.ADMIN and preparation:
        identity = await db.get(IdentidadInfraestructura, service.identidad_infraestructura_id)
        result['verificacion_instancia'] = {'servicio_id': service.id, 'definicion_id': str(service.definicion_version_id),
            'preparacion_id': str(preparation.id), 'resource_uuid': str(identity.resource_uuid) if identity else None,
            'nonce_sha256': metadata.get('nonce_sha256'), 'endpoint': metadata.get('endpoint')}
    return actor, service, result


async def metadatos(db, *, actor, servicio_id):
    return (await _context(db, actor, servicio_id))[2]


async def revelar(db, *, actor, servicio_id):
    actor, service, result = await _context(db, actor, servicio_id)
    if not result['puede_revelar_credenciales']:
        raise error(409, 'acceso_no_preparado', 'El acceso inicial no está habilitado para este estado y usuario')
    try:
        values = configured_keyring().decrypt(service.credenciales_encrypted, context=f'servicio:{service.id}:secretos')
        field = {'linux': 'guest_password', 'postgresql': 'database_password', 'bookstack': 'teacher_password', 'drawio': 'access_password'}[result['producto']]
        password = values[field]
        username = (service.acceso_metadata or {})['username']
        if not isinstance(password, str) or not password or not isinstance(username, str) or not username:
            raise ValueError()
    except (SecretError, ValueError, KeyError, TypeError):
        raise error(409, 'acceso_no_preparado', 'No se pudo recuperar el acceso inicial autorizado') from None
    credentials = {'usuario': username, 'password': password}
    if result['producto'] == 'postgresql':
        metadata = service.acceso_metadata
        credentials.update(host=metadata['host'], puerto=metadata['port'], base=metadata['database'], sslmode='verify-full')
    db.add(EventoSeguridad(actor_usuario_id=actor.id, accion='revelar_acceso_servicio', resultado='completado',
        referencia=f'servicio:{service.id}', motivo=result['estado_entrega']))
    await db.flush()
    return {'servicio_id': service.id, 'estado_entrega': result['estado_entrega'], 'metodo': result['metodo'],
        'direccion': result['direccion'], 'credenciales': credentials, 'instrucciones': result['instrucciones']}
