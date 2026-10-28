"""Perfiles de aplicaciones: consulta sin efectos ni habilitación implícita."""
from app.config import get_settings
from app.schemas.application_profiles import ProfileRegistry, ProfileError
from app.utils.errors import error


def _registry(settings):
    return ProfileRegistry(settings.application_profiles)


def profile_capabilities(*, settings=None):
    try:
        return _registry(settings or get_settings()).capabilities()
    except ProfileError:
        raise error(409, 'perfil_aplicacion_no_disponible', 'La configuración de aplicaciones requiere revisión de infraestructura') from None


def _motivo_perfil_no_disponible(reference, *, settings=None, reason_code=None):
    cfg = settings or get_settings()
    if reason_code == 'PLATFORM_CHANGED':
        return 'El nodo de infraestructura cambió su versión de sistema y requiere revalidar el perfil Docker antes de aprobar o desplegar'
    if reason_code == 'DEPENDENCY_UNAVAILABLE':
        return 'El nodo de infraestructura no tiene disponibles las dependencias para ejecutar aplicaciones en este momento'
    if isinstance(reference, dict):
        key = f"{reference.get('id')}:{reference.get('revision')}"
        entry = (cfg.application_profiles or {}).get(key)
        if entry:
            estado = entry.get('estado')
            motivo = entry.get('motivo_codigo')
            if estado == 'bloqueado':
                if motivo == 'PLATFORM_CHANGED':
                    return 'El nodo de infraestructura cambió su versión de sistema y requiere revalidar el perfil Docker antes de aprobar o desplegar'
                if motivo == 'DEPENDENCY_UNAVAILABLE':
                    return 'El nodo de infraestructura no tiene disponibles las dependencias para ejecutar aplicaciones en este momento'
                return 'El perfil de infraestructura para esta aplicación se encuentra bloqueado y requiere revisión'
            if estado == 'pendiente_validacion':
                return 'Esta aplicación todavía no está habilitada en la infraestructura seleccionada'
            if entry.get('sha256') != reference.get('sha256'):
                return 'El perfil de infraestructura cambió; actualizá la aplicación desde el Catálogo de servicios antes de aprobar'
        elif any(k.startswith(f"{reference.get('id')}:") and v.get('estado') == 'habilitado' for k, v in (cfg.application_profiles or {}).items()):
            return 'El perfil de infraestructura cambió; actualizá la aplicación desde el Catálogo de servicios antes de aprobar'
    return 'Esta aplicación todavía no está habilitada en la infraestructura seleccionada'


def require_profile(reference, *, settings=None, **context):
    try:
        return _registry(settings or get_settings()).require(reference, **context)
    except ProfileError:
        raise error(409, 'perfil_aplicacion_no_disponible', _motivo_perfil_no_disponible(reference, settings=settings)) from None


async def verify_node_profile(reference, *, node, runner=None, settings=None):
    """Consulta el estado real del perfil en el nodo antes de reservar o desplegar."""
    cfg = settings or get_settings()
    if runner is None and not (isinstance(cfg.runner_nodes, dict) and node in cfg.runner_nodes):
        return
    from app.services.application_job_client import ApplicationJobClient
    from app.services.guest_runner_client import RunnerError
    from infra.applications.job.protocol import PROTOCOL, JobError, canonical, parse_response
    client = runner if runner is not None else ApplicationJobClient(config=cfg.runner_nodes, timeout_seconds=5, query_retries=0)
    if runner is None:
        try:
            client.validar_destino(node)
        except RunnerError:
            return
    request = {'protocol': PROTOCOL, 'action': 'profiles'}
    try:
        raw_reply = await client.execute(request, node=node)
        reply = parse_response(canonical(raw_reply), request=request) if isinstance(raw_reply, dict) else parse_response(raw_reply, request=request)
    except JobError:
        raise error(409, 'perfil_aplicacion_no_disponible', 'No se pudo verificar el perfil de aplicaciones en el nodo seleccionado') from None
    if not reply.get('ok'):
        raise error(409, 'perfil_aplicacion_no_disponible', 'El nodo seleccionado todavía no admite esta aplicación')
    profiles = reply.get('data', {}).get('profiles', [])
    matched = next((p for p in profiles if p.get('id') == reference.get('id') and p.get('revision') == reference.get('revision')), None)
    if matched is None:
        raise error(409, 'perfil_aplicacion_no_disponible', 'El nodo todavía no tiene configurado el perfil para esta aplicación')
    if matched.get('estado') != 'habilitado':
        raise error(409, 'perfil_aplicacion_no_disponible', _motivo_perfil_no_disponible(reference, settings=cfg, reason_code=matched.get('motivo_codigo')))
    if matched.get('sha256') != reference.get('sha256'):
        raise error(409, 'perfil_aplicacion_no_disponible', 'El perfil del nodo cambió; actualizá el catálogo o el nodo antes de aprobar')

