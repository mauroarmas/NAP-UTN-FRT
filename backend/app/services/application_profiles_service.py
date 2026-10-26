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


def require_profile(reference, *, settings=None, **context):
    try:
        return _registry(settings or get_settings()).require(reference, **context)
    except ProfileError:
        raise error(409, 'perfil_aplicacion_no_disponible', 'Esta aplicación todavía no está habilitada en la infraestructura seleccionada') from None
