"""One bounded PaaS recipe on the existing Docker/LXC engine."""
from app.config import get_settings
from app.services.oci_registry_service import reference
from app.utils.errors import error

REPOSITORY='docker.io/library/mariadb'
VARIABLES={'MARIADB_DATABASE':'catedra','MARIADB_USER':'docente','MARIADB_ROOT_HOST':'localhost'}
SECRET_NAMES={'MARIADB_PASSWORD','MARIADB_ROOT_PASSWORD'}


def is_reference(image):
    host,repository,_=reference(image)
    return host+'/'+repository==REPOSITORY


def require_validation(profile,image):
    proof=get_settings().mariadb_application_validation
    if (not isinstance(proof,dict) or proof.get('tipo')!='proxmox_real'
            or proof.get('perfil')!=profile or proof.get('manifest_digest')!=image['manifest_digest']
            or not {'aislamiento','tls','autenticacion','persistencia','recuperacion'}<=set(proof.get('comprobaciones',[]))):
        raise error(409,'mariadb_pendiente_validacion','MariaDB todavía necesita completar su comprobación real en la infraestructura.')


def require_document(document):
    if (document['imagen']['repositorio']!=REPOSITORY or document['modelo_servicio']!='paas'
            or document['access']!={'tipo':'tcp','puerto':3306,'politica':'mariadb-tls',
                'probe':{'tipo':'mariadb_select_1','timeout_segundos':10}}
            or document['variables']!=VARIABLES or document['persistencia']!=['/var/lib/mysql']
            or {s['nombre'] for s in document['secretos']}!=SECRET_NAMES
            or any(s['modo']!='generado' for s in document['secretos'])):
        raise error(422,'mariadb_configuracion_invalida','Usá la configuración preparada de MariaDB para prácticas.')
    require_validation(document['perfil'],document['imagen'])
