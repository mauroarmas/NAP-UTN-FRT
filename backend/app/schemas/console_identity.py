"""Protocolo cerrado nap-console-identity/1 (feature 022); sólo biblioteca estándar, se instala igual en el nodo.

Identidades individuales de consola: crear/actualizar, retirar, terminar sesiones y comprobar. La contraseña viaja
sólo por stdin y nunca aparece en una respuesta. Nada de lo que no esté en este contrato se acepta.
"""
import re
from uuid import UUID

try:  # Portal y pruebas del repositorio.
    from app.schemas.guest_runner import RunnerError, parse_json
except ImportError:  # Nodo: módulos hermanos copiados por el instalador.
    from protocol import RunnerError, parse_json


PROTOCOL = 'nap-console-identity/1'
ACTIONS = {'ensure', 'retire', 'end_sessions', 'probe'}
BASE_FIELDS = {'protocol', 'operation_id', 'action', 'cluster_uuid', 'identidad', 'revision'}
EXTRA = {'ensure': {'password_consola', 'pools'}, 'retire': set(), 'end_sessions': {'vmids'}, 'probe': set()}
MAX_BYTES = 65536
MAX_ITEMS = 200
IDENTIDAD = re.compile(r'nap-u[0-9]{1,12}@pve')
POOL = re.compile(r'catedra-[0-9]{1,9}')
PASSWORD = re.compile(r'[A-Za-z0-9_-]{32,128}')
ROL = 'NapConsola'


def _uuid(value):
    return isinstance(value, str) and str(UUID(value)) == value


def _pools(value):
    if (not isinstance(value, list) or len(value) > MAX_ITEMS or len(set(value)) != len(value)
            or not all(isinstance(p, str) and POOL.fullmatch(p) for p in value)):
        raise ValueError()


def parse_request(raw):
    """Valida el JSON recibido; cualquier desvío es INVALID_REQUEST (sin detalle)."""
    try:
        if not isinstance(raw, bytes) or len(raw) > MAX_BYTES:
            raise ValueError()
        value = parse_json(raw, limit=MAX_BYTES)
        if not isinstance(value, dict) or value.get('protocol') != PROTOCOL or value.get('action') not in ACTIONS:
            raise ValueError()
        action = value['action']
        expected = BASE_FIELDS | EXTRA[action]
        if action == 'retire' and 'pools' in value:
            expected = expected | {'pools'}      # `pools` es opcional en retire: ausente = retirar todo
        if set(value) != expected:
            raise ValueError()
        if not (_uuid(value['operation_id']) and _uuid(value['cluster_uuid'])):
            raise ValueError()
        if type(value['revision']) is not int or not 1 <= value['revision'] <= 1000000:
            raise ValueError()
        if not isinstance(value['identidad'], str) or not IDENTIDAD.fullmatch(value['identidad']):
            raise ValueError()
        if 'pools' in value:
            _pools(value['pools'])
        if action == 'ensure' and not (isinstance(value['password_consola'], str) and PASSWORD.fullmatch(value['password_consola'])):
            raise ValueError()
        if action == 'end_sessions':
            vmids = value['vmids']
            if (not isinstance(vmids, list) or not 1 <= len(vmids) <= MAX_ITEMS or len(set(vmids)) != len(vmids)
                    or not all(type(v) is int and 100 <= v <= 999999999 for v in vmids)):
                raise ValueError()
        return value
    except (ValueError, TypeError):
        raise RunnerError('INVALID_REQUEST') from None
    except RunnerError:
        raise


RESPONSE_FIELDS = {'protocol', 'operation_id', 'action', 'identidad', 'status', 'phase', 'identity_verified',
    'observed_at', 'result', 'error'}
RESULT_FIELDS = {
    'ensure': {'pools_aplicados', 'pools_pendientes', 'creada', 'password'},
    'retire': {'retirada', 'pools_quitados'},
    'end_sessions': {'terminadas'},
    'probe': {'existe', 'pools', 'roles'},
}
PASSWORD_ESTADOS = {'aplicada', 'sin_cambios'}
ERROR_CODES = {'INVALID_REQUEST', 'IDENTITY_MISMATCH', 'ROLE_UNAVAILABLE', 'PROBE_FAILED', 'UNCONFIRMED',
    'DEADLINE_EXCEEDED', 'RUNNER_UNAVAILABLE'}


def _validar_resultado(action, result):
    if not isinstance(result, dict) or not set(result) <= RESULT_FIELDS[action]:
        raise ValueError()
    for clave in ('pools_aplicados', 'pools_pendientes', 'pools_quitados', 'pools'):
        if clave in result:
            _pools(result[clave])
    for clave in ('creada', 'retirada', 'existe'):
        if clave in result and not isinstance(result[clave], bool):
            raise ValueError()
    if 'password' in result and result['password'] not in PASSWORD_ESTADOS:
        raise ValueError()
    if 'terminadas' in result and (type(result['terminadas']) is not int or not 0 <= result['terminadas'] <= 100000):
        raise ValueError()
    if 'roles' in result and (not isinstance(result['roles'], list) or any(r != ROL for r in result['roles'])):
        raise ValueError()


def parse_response(raw, request):
    """Acepta sólo la respuesta del mismo pedido; un código desconocido se trata como sin confirmar."""
    try:
        value = parse_json(raw, limit=MAX_BYTES)
        if (not isinstance(value, dict) or not set(value) <= RESPONSE_FIELDS or value.get('protocol') != PROTOCOL
                or any(value.get(k) != request[k] for k in ['operation_id', 'action', 'identidad'])
                or value.get('status') not in {'succeeded', 'failed', 'unconfirmed'}):
            raise ValueError()
        if value['status'] == 'succeeded':
            if value.get('identity_verified') is not True:
                raise ValueError()
            _validar_resultado(request['action'], value.get('result'))
        else:
            error = value.get('error')
            if not isinstance(error, dict) or error.get('code') not in ERROR_CODES:
                value['error'] = {'code': 'UNCONFIRMED', 'retryable': True}
        return value
    except (ValueError, TypeError, KeyError, RunnerError):
        raise RunnerError('UNCONFIRMED') from None
