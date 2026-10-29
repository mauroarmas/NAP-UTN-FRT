"""Node validation of the dedicated exported contract, with closed policy checks.

jsonschema is an explicit dependency of the application runner package. A missing
dependency must prevent admission; it must never fall back to an unchecked dict.
"""
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
import re

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from .protocol import JobError, canonical


@lru_cache
def _contract():
    schema = json.loads((Path(__file__).resolve().parents[1] / 'schemas/nap-deployment-1.json').read_text())
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema), schema['x-nap-policy']


def _strict(value, depth=0):
    if depth > 16 or type(value) not in {dict, list, str, int, bool, type(None)}: raise ValueError()
    if type(value) is dict:
        for k, v in value.items():
            if type(k) is not str: raise ValueError()
            _strict(v, depth+1)
    if type(value) is list:
        for v in value: _strict(v, depth+1)


def validate_configuration(value):
    try:
        _strict(value)
        if len(canonical(value)) > 65536: raise ValueError()
        validator, policy = _contract()
        validator.validate(value)
        names = list(value['variables']) + [s['nombre'] for s in value['secretos']]
        if (len(names) > 20 or len(names) != len(set(names))
                or any(not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,63}', n)
                    or n in policy['reserved_variables'] or n.startswith(('LD_', 'NAP_', 'BASH_FUNC_')) for n in names)):
            raise ValueError()
        if any('\x00' in v or len(v.encode('utf-8')) > 4096 for v in value['variables'].values()): raise ValueError()
        paths = value['persistencia']
        if len(paths) != len(set(paths)): raise ValueError()
        for p in paths:
            if (not re.fullmatch(r'/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*', p)
                    or len(p) > 255 or any(s in {'.', '..'} for s in p.split('/'))
                    or any(p == f or p.startswith(f + '/') for f in policy['forbidden_targets'])):
                raise ValueError()
        access, base = value['access'], value['base']
        if access['tipo'] == 'web':
            probe = access['probe']
            if (any(p in {'.', '..'} for p in probe['path'].split('/'))
                    or len(probe['estados']) != len(set(probe['estados']))): raise ValueError()
        if value['origen'] == 'imagen_docker':
            image = value['imagen']
            if ((base['os'], base['version']) != ('ubuntu', '24.04')
                    or image['arquitectura'] != base['arquitectura']): raise ValueError()
            if access['tipo']=='tcp' and (image['repositorio']!='docker.io/library/mariadb'
                    or value['modelo_servicio']!='paas' or access['puerto']!=3306
                    or value['persistencia']!=['/var/lib/mysql']
                    or value['variables']!={'MARIADB_DATABASE':'catedra','MARIADB_USER':'docente','MARIADB_ROOT_HOST':'localhost'}
                    or {s['nombre'] for s in value['secretos']}!={'MARIADB_PASSWORD','MARIADB_ROOT_PASSWORD'}
                    or any(s['modo']!='generado' for s in value['secretos'])):
                raise ValueError()
        else:
            source = value['community']; slug = source['slug']
            allowed = {'mariadb': ('mariadb-tls', {'phpmyadmin': 'no'}), 'caddy': ('caddy-web', {'xcaddy': 'no'})}
            if (slug not in allowed or source['identidad_externa'] != f'ct/{slug}.sh'
                    or source['instalador'] != f'install/{slug}-install.sh'
                    or (source['postconfiguracion'], source['respuestas']) != allowed[slug]
                    or (base['os'], base['version']) != ('debian', '13')
                    or value['minimum_resources'] != {'vcpus': 2, 'ram_mb': 1024, 'disk_gb': 8}
                    or (slug == 'mariadb') != (access['tipo'] == 'tcp')): raise ValueError()
        return json.loads(canonical(value))
    except (ValidationError, ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        raise JobError('INVALID_REQUEST') from None


def configuration_digest(value):
    return sha256(canonical(validate_configuration(value))).hexdigest()
