"""The guest's typed TLS probe follows host confinement and bridge checks."""
import os
import stat
from pathlib import Path

from ..job.protocol import JobError, strict_json

# La primera inicialización de una base de datos depende del almacenamiento del nodo (en NFS o discos
# lentos supera los 120 s). La espera es acotada y se puede ajustar por nodo con un archivo opcional de
# root; sin archivo rigen los valores por defecto. Nunca se acepta una espera ilimitada.
LIMITS_PATH = Path('/etc/nap/applications-011/limits.json')
LIMITS_SCHEMA = 'nap-application-limits/1'
WAIT_KEYS = {'database': 'espera_base_datos_segundos', 'web': 'espera_web_segundos'}
WAIT_DEFAULTS = {'database': 300, 'web': 90}
WAIT_BOUNDS = {'database': (60, 600), 'web': (30, 600)}   # < 900 s del proceso hijo del nodo


def ready_wait(kind, *, path=None):
    """Segundos máximos para que la aplicación acepte la comprobación después de arrancar."""
    path = Path(path or LIMITS_PATH)
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return WAIT_DEFAULTS[kind]
    except OSError:
        raise JobError('PROFILE_UNAVAILABLE') from None
    try:
        with os.fdopen(descriptor, 'rb') as source:
            info = os.fstat(source.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid not in {0, os.geteuid()} or info.st_mode & 0o022
                    or info.st_nlink != 1 or info.st_size > 4096): raise ValueError()
            value = strict_json(source.read(4097), limit=4096)
        if (type(value) is not dict or value.get('schema_version') != LIMITS_SCHEMA
                or not set(value) <= {'schema_version', *WAIT_KEYS.values()}): raise ValueError()
        for name, key in WAIT_KEYS.items():
            if key in value:
                low, high = WAIT_BOUNDS[name]
                if type(value[key]) is not int or not low <= value[key] <= high: raise ValueError()
        return value.get(WAIT_KEYS[kind], WAIT_DEFAULTS[kind])
    except Exception:
        raise JobError('PROFILE_UNAVAILABLE') from None


def verify(context,payload):
    context.node.assert_confinement(context.identity)
    database=context.configuration['access']['tipo']=='tcp'
    request={**payload,'tls':{'ca_pem':context.tls['ca_pem']},'espera_segundos':ready_wait('database' if database else 'web')}
    if database:request['private_values']={'MARIADB_PASSWORD':context.secret('MARIADB_PASSWORD')}
    context.node.docker_action(context.identity,'probe',request,context)
    return {'recurso_configurado':True,'comprobaciones':['aislamiento','runtime','salud','autenticacion_tcp' if database else 'acceso_web']}
