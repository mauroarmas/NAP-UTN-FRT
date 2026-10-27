"""Acceso Draw.io con NAP: origen aislado, códigos de un uso y permisos actuales."""
from datetime import timedelta
import hashlib
import ipaddress
import re
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import select, update

from app.config import get_settings
from app.models.acceso_aplicacion import AccesoAplicacion
from app.models.autenticacion import SesionAutenticacion
from app.models.identidad_infraestructura import IdentidadInfraestructura
from app.models.definicion_servicio import DefinicionServicio
from app.models.usuario import Usuario
from app.models.servicio import EstadoServicio
from app.services import auth_service as auth
from app.services.acceso_service import requiere_acceso_servicio
from app.utils.clock import clock, db_utc
from app.utils.errors import error
from app.utils.secretos import configured_keyring, SecretError

COOKIE = '__Host-nap_app'


def configurado():
    settings = get_settings()
    domain = settings.application_gateway_domain
    portals = [urlsplit(origin).hostname for origin in {settings.app_frontend_url, *settings.auth_allowed_origins}]
    # No alojar aplicaciones bajo el host del portal: incluso sus cookies de
    # desarrollo deben quedar fuera de las solicitudes a software externo.
    return bool(len(domain) <= 160 and len(domain.split('.')) >= 2
        and all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?',label) for label in domain.split('.'))
        and all(not host or (domain != host and not domain.endswith('.'+host)) for host in portals)
        and settings.application_gateway_ca_file)


def origen(servicio_id):
    if not configurado():
        raise error(503, 'acceso_nap_no_configurado', 'Falta configurar el acceso a las aplicaciones con NAP.')
    settings = get_settings()
    host = f'app-{servicio_id}.{settings.application_gateway_domain}'
    port = '' if settings.application_gateway_port == 443 else ':' + str(settings.application_gateway_port)
    return 'https://' + host + port


def servicio_del_host(request):
    settings = get_settings()
    host = request.url.hostname or ''
    match = re.fullmatch(r'app-([1-9][0-9]{0,9})\.' + re.escape(settings.application_gateway_domain), host)
    if not configurado() or not match:
        raise error(404, 'aplicacion_no_encontrada', 'Aplicación no encontrada.')
    identity = int(match[1])
    if request.url.scheme != 'https' or str(request.url).split('/', 3)[:3] != origen(identity).split('/')[:3]:
        raise error(403, 'origen_no_permitido', 'La dirección de acceso no está autorizada.')
    return identity


async def sesion_vigente(db, identity):
    from app.services.restauracion_service import exigir_habilitacion, exigir_acceso_reemitido
    await exigir_habilitacion(db, componente='api')
    session = await db.get(SesionAutenticacion, identity, populate_existing=True)
    user = await db.get(Usuario, session.usuario_id, populate_existing=True) if session else None
    if (not session or not user or not user.activo or user.debe_cambiar_password or session.revoked_at
        or session.proposito != 'operativo' or db_utc(session.expira_at) <= clock.now()
        or session.auth_version != user.auth_version or (user.totp_habilitado and not session.mfa_verified_at)):
        raise error(401, 'sesion_invalida', 'Tu sesión de NAP terminó. Volvé al portal para abrir la aplicación.')
    await exigir_acceso_reemitido(db, user)
    return user, session


async def autorizar(db, actor, servicio_id):
    # El alcance se comprueba antes de recuperar credenciales o construir destinos.
    service = await requiere_acceso_servicio(db, actor, servicio_id)
    if service.configuracion_despliegue_id:
        from app.services.application_target_service import destination
        from app.services.service_access_service import preparacion_confirmada
        from app.services.vigencia_service import exigir_cobertura
        await exigir_cobertura(db,service.id,clock.now())
        if (service.estado!=EstadoServicio.RUNNING or service.disponibilidad_aplicacion!='utilizable'
                or not await preparacion_confirmada(db,service)):
            raise error(409,'aplicacion_no_disponible','La aplicación debe estar disponible antes de abrirla.')
        identity,instance=await destination(db,service)
        if instance['access']['tipo']!='web':
            raise error(409,'aplicacion_no_compatible','Este servicio utiliza acceso nativo.')
        return service,identity,instance
    definition = await db.get(DefinicionServicio, service.definicion_version_id) if service.definicion_version_id else None
    if not definition or definition.producto != 'drawio':
        raise error(409, 'aplicacion_no_compatible', 'Este servicio no admite acceso con NAP.')
    from app.services.service_access_service import preparacion_confirmada
    from app.services.vigencia_service import exigir_cobertura
    await exigir_cobertura(db, service.id, clock.now())
    if service.estado != EstadoServicio.RUNNING or not await preparacion_confirmada(db, service):
        raise error(409, 'aplicacion_no_disponible', 'La aplicación debe estar iniciada antes de abrirla.')
    identity = await db.get(IdentidadInfraestructura, service.identidad_infraestructura_id)
    metadata = service.acceso_metadata or {}
    settings = get_settings()
    try:
        profile_id = metadata.get('bootstrap_network_profile_id') or metadata['network_profile_id']
        profile = settings.network_profiles[profile_id]
        instance = profile['instances'][str(identity.resource_uuid)]
        endpoint = urlsplit(metadata['endpoint'])
        address = ipaddress.ip_address(instance['address'])
        if (identity.ausencia_confirmada_at or identity.servicio_id != service.id or identity.estado != 'materializada'
            or not identity.ownership_verificada_at or identity.cluster_id != settings.infrastructure_profile['cluster_id']
            or identity.nodo not in profile['nodes'] or endpoint.scheme != 'https'
            or endpoint.hostname != instance['host'] or endpoint.port not in (None,443)
            or endpoint.username or endpoint.password or endpoint.path not in ('','/') or endpoint.query or endpoint.fragment
            or metadata['host'] != instance['host'] or instance['address'] not in metadata['addresses']
            or not any(address in ipaddress.ip_network(cidr) for cidr in profile['allowed_cidrs']
                       if ipaddress.ip_network(cidr).version == address.version)):
            raise ValueError()
    except (ValueError, KeyError, TypeError, AttributeError):
        raise error(409, 'destino_no_confirmado', 'No se pudo confirmar la dirección de esta aplicación.') from None
    return service, identity, instance


async def crear_codigo(db, servicio_id, *, actor, session):
    if not configurado(): origen(servicio_id)
    owner, current_session = await sesion_vigente(db, session.id)
    if owner.id != actor.id:
        raise error(403, 'sin_permisos', 'La sesión no corresponde a esta cuenta.')
    await autorizar(db, actor, servicio_id)
    import secrets
    code = secrets.token_urlsafe(32)
    now = clock.now()
    db.add(AccesoAplicacion(codigo_sha256=hashlib.sha256(code.encode()).hexdigest(), sesion_id=current_session.id,
        servicio_id=servicio_id, creado_at=now, expira_at=min(now+timedelta(seconds=60),db_utc(current_session.expira_at))))
    auth.auditar(db, actor, 'abrir_aplicacion', referencia=f'servicio:{servicio_id}')
    await db.flush()
    return {'destino': origen(servicio_id) + '/_nap/entrar', 'codigo': code}


async def consumir_codigo(db, request, code):
    servicio_id = servicio_del_host(request)
    if request.headers.get('origin') not in {get_settings().app_frontend_url, *get_settings().auth_allowed_origins}:
        raise error(403, 'origen_no_permitido', 'Abrí la aplicación desde NAP.')
    if not isinstance(code,str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}',code):
        raise error(401, 'apertura_invalida', 'Volvé a abrir la aplicación desde NAP.')
    row = await db.scalar(update(AccesoAplicacion).where(
        AccesoAplicacion.codigo_sha256==hashlib.sha256(code.encode()).hexdigest(),
        AccesoAplicacion.servicio_id==servicio_id, AccesoAplicacion.consumido_at.is_(None),
        AccesoAplicacion.expira_at>clock.now()).values(consumido_at=clock.now()).returning(AccesoAplicacion)
        .execution_options(synchronize_session=False,populate_existing=True))
    if not row:
        raise error(401, 'apertura_invalida', 'Este acceso venció o ya fue usado. Volvé a abrir la aplicación desde NAP.')
    actor, session = await sesion_vigente(db,row.sesion_id)
    await autorizar(db,actor,servicio_id)
    value={'sesion':str(session.id),'servicio':servicio_id,'exp':int(db_utc(session.expira_at).timestamp())}
    cookie=configured_keyring().encrypt(value,context='nap-app:'+request.url.hostname)
    return cookie,session


async def autenticar_aplicacion(db,request):
    servicio_id = servicio_del_host(request)
    try:
        value=configured_keyring().decrypt(request.cookies.get(COOKIE,''),context='nap-app:'+request.url.hostname)
        if value['servicio']!=servicio_id or type(value['exp']) is not int or value['exp']<=clock.now().timestamp():raise ValueError()
        session_id=UUID(value['sesion'])
    except (SecretError,KeyError,ValueError,TypeError):
        raise error(401,'sesion_aplicacion_invalida','Abrí esta aplicación desde tu sesión de NAP.') from None
    actor,session=await sesion_vigente(db,session_id)
    if value['exp']!=int(db_utc(session.expira_at).timestamp()):
        raise error(401,'sesion_aplicacion_invalida','Abrí nuevamente la aplicación desde NAP.')
    service,identity,instance=await autorizar(db,actor,servicio_id)
    return actor,session,service,identity,instance


def credenciales(service):
    try:
        values=configured_keyring().decrypt(service.credenciales_encrypted,context=f'servicio:{service.id}:secretos')
        username=service.acceso_metadata['username'];password=values['access_password']
        if not isinstance(username,str) or not re.fullmatch(r'nap_[a-f0-9]{32}',username) or not isinstance(password,str) or not re.fullmatch(r'[A-Za-z0-9_-]{20,128}',password):raise ValueError()
        return username,password
    except (SecretError,KeyError,TypeError,ValueError):
        raise error(409,'acceso_interno_no_disponible','No se pudo abrir la aplicación. Avisá a administración.') from None


async def confirmar_apertura(db,request):
    """Acredita la respuesta HTTPS a través de NAP, sin simular una prueba externa."""
    from app.services.capacidad_service import BloqueoCapacidad
    from app.models.servicio import Servicio
    await BloqueoCapacidad(db).__aenter__()
    await db.scalar(select(Servicio).where(Servicio.id==servicio_del_host(request)).with_for_update().execution_options(populate_existing=True))
    actor,session,service,identity,_=await autenticar_aplicacion(db,request)
    if (not service.acceso_metadata.get('gateway_verified') or
        service.acceso_metadata.get('gateway_preparacion_id') != service.acceso_metadata.get('preparacion_id')):
        from app.models.pedido import Pedido,EstadoPedido
        from app.services import pedido_service,notificacion_service
        service.acceso_metadata={**service.acceso_metadata,'gateway_verified':True,'gateway_verified_at':clock.now().isoformat(),
            'gateway_preparacion_id':service.acceso_metadata['preparacion_id']}
        service.disponibilidad_aplicacion='utilizable'
        service.acceso_red_verificado_at=service.verificado_at=clock.now()
        pedido=await db.get(Pedido,service.pedido_id) if service.pedido_id else None
        if pedido and pedido.estado==EstadoPedido.EN_DESPLIEGUE:
            await pedido_service.transicionar(db,pedido.id,EstadoPedido.ACTIVO,usuario=actor,
                motivo='Acceso HTTPS confirmado mediante la sesión de NAP',evento_clave=f'gateway:{service.id}:entrega')
            await notificacion_service.encolar_aviso_pedido(db,pedido,evento=f'gateway:{service.id}:entrega',tipo='servicio_disponible',
                asunto=f'Pedido #{pedido.id}: servicio disponible',texto='El acceso con NAP está habilitado. Podés abrir la aplicación desde Servicios.',destinatarios='ambos',solo_portal=True)
        auth.auditar(db,actor,'acceso_aplicacion_confirmado',referencia=f'servicio:{service.id}')
    await db.commit()
