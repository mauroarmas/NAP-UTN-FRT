"""Known access requirements, independent of image tags and infrastructure state.

Metadata validation cannot prove that an arbitrary image serves HTTP. Keep known
unsupported applications out of the offer without executing an image at intake.
"""
from app.services.oci_registry_service import reference
from app.utils.errors import error


NATIVE_SERVICES = {
    'docker.io/library/redis': 'Redis',
    'docker.io/library/mariadb': 'MariaDB',
    'docker.io/library/mysql': 'MySQL',
    'docker.io/library/postgres': 'PostgreSQL',
}


def incompatibility(image):
    host, repository, _ = reference(image)
    name = NATIVE_SERVICES.get(host + '/' + repository)
    if host+'/'+repository=='docker.io/library/mariadb':
        from fastapi import HTTPException
        from app.config import get_settings
        from app.services.application_profiles_service import require_profile
        from app.services.mariadb_application_service import require_validation
        proof=get_settings().mariadb_application_validation
        try:
            ref=proof.get('perfil',{})
            require_profile(ref)
            require_validation(ref,{'manifest_digest':proof.get('manifest_digest')})
            return None
        except HTTPException:pass
    if name:
        return (f'{name} necesita una conexión de datos. NAP todavía no tiene un adaptador '
                'para instalarlo, comprobarlo y entregar esa conexión de forma segura. '
                'Reintentar el mismo despliegue no resuelve esta limitación.')
    return None


def require_image(image):
    reason = incompatibility(image)
    if reason:
        raise error(422, 'aplicacion_no_compatible', reason)


def require_document(document):
    if document['origen'] != 'imagen_docker':
        return
    image = document['imagen']
    if document.get('access',{}).get('tipo')=='tcp':
        from app.services.mariadb_application_service import require_document as require_mariadb
        require_mariadb(document)
        return
    if image['repositorio']=='docker.io/library/mariadb':
        raise error(422,'aplicacion_no_compatible',
            'Esta configuración antigua de MariaDB usa acceso web. Agregá MariaDB 11.4 con el adaptador de base de datos preparado.')
    require_image(image['repositorio'] + '@' + image['manifest_digest'])
    access = document['access']
    if access['tipo'] != 'web' or access['upstream'] != 'http':
        raise error(422, 'aplicacion_no_compatible',
                    'NAP todavía no tiene un adaptador para entregar este tipo de conexión.')
