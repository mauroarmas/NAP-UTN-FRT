"""Protocolo cerrado nap-iaas-access/1; solo biblioteca estándar, se instala igual en el nodo."""
import ipaddress
import re
from uuid import UUID

try:  # Portal y pruebas del repositorio.
    from app.schemas.guest_runner import RunnerError, parse_json
    from app.utils.ssh_keys import ClaveSshInvalida, validar_clave
except ImportError:  # Nodo: módulos hermanos copiados por el instalador.
    from protocol import RunnerError, parse_json
    from ssh_keys import ClaveSshInvalida, validar_clave


PROTOCOL = 'nap-iaas-access/1'
USUARIO = 'nap'
ACTIONS = {'configure', 'probe'}
BASE_FIELDS = {'protocol', 'operation_id', 'action', 'cluster_uuid', 'resource_uuid', 'node', 'vmid', 'pool',
    'nonce', 'revision', 'usuario'}
MAX_BYTES = 16384


def _uuid(value):
    return isinstance(value, str) and str(UUID(value)) == value


def parse_request(raw):
    """Valida el JSON recibido; devuelve el diccionario con la clave ya normalizada y su huella."""
    try:
        if not isinstance(raw, bytes) or len(raw) > MAX_BYTES:
            raise ValueError()
        value = parse_json(raw, limit=MAX_BYTES)
        if not isinstance(value, dict) or value.get('protocol') != PROTOCOL or value.get('action') not in ACTIONS:
            raise ValueError()
        action = value['action']
        expected = BASE_FIELDS | ({'clave_publica'} if action == 'configure' else {'huella'})
        if set(value) != expected:
            raise ValueError()
        if not all(_uuid(value[key]) for key in ['operation_id', 'cluster_uuid', 'resource_uuid']):
            raise ValueError()
        if type(value['vmid']) is not int or not 100 <= value['vmid'] <= 999999999:
            raise ValueError()
        if type(value['revision']) is not int or not 1 <= value['revision'] <= 1000000:
            raise ValueError()
        if value['usuario'] != USUARIO:
            raise ValueError()
        for key, pattern in {'node': r'[a-zA-Z0-9][a-zA-Z0-9-]{0,62}', 'pool': r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,99}',
            'nonce': r'[a-zA-Z0-9_-]{22,128}'}.items():
            if not isinstance(value[key], str) or not re.fullmatch(pattern, value[key]):
                raise ValueError()
        if action == 'configure':
            _, normalizada, huella = validar_clave(value['clave_publica'])
            value = {**value, 'clave_publica': normalizada, 'huella': huella}
        elif not isinstance(value['huella'], str) or not re.fullmatch(r'SHA256:[A-Za-z0-9+/]{43}', value['huella']):
            raise ValueError()
        return value
    except (ValueError, TypeError, ClaveSshInvalida):
        raise RunnerError('INVALID_REQUEST') from None
    except RunnerError:
        raise


RESPONSE_FIELDS = {'protocol', 'operation_id', 'action', 'resource_uuid', 'status', 'phase', 'identity_verified',
    'observed_at', 'result', 'error'}
RESULT_FIELDS = {'ready', 'revision', 'huella', 'usuario', 'puerto', 'direccion'}
ERROR_CODES = {'INVALID_REQUEST', 'IDENTITY_MISMATCH', 'GUEST_NOT_RUNNING', 'SSHD_UNAVAILABLE', 'SUDO_UNAVAILABLE',
    'PROBE_FAILED', 'UNCONFIRMED', 'DEADLINE_EXCEEDED', 'RUNNER_UNAVAILABLE'}


def parse_response(raw, request):
    """Acepta sólo la respuesta del mismo pedido; un código desconocido se trata como sin confirmar."""
    try:
        value = parse_json(raw, limit=65536)
        if (not isinstance(value, dict) or not set(value) <= RESPONSE_FIELDS or value.get('protocol') != PROTOCOL
            or any(value.get(key) != request[key] for key in ['operation_id', 'action', 'resource_uuid'])
            or value.get('status') not in {'succeeded', 'failed', 'unconfirmed'}):
            raise ValueError()
        if value['status'] == 'succeeded':
            result = value.get('result')
            if (not isinstance(result, dict) or not set(result) <= RESULT_FIELDS or result.get('ready') is not True
                or value.get('identity_verified') is not True):
                raise ValueError()
            if 'direccion' in result:
                if not isinstance(result['direccion'], str):
                    raise ValueError()
                ipaddress.IPv4Address(result['direccion'])  # ValueError si no es una IPv4
        else:
            error = value.get('error')
            if not isinstance(error, dict) or error.get('code') not in ERROR_CODES:
                value['error'] = {'code': 'UNCONFIRMED', 'retryable': True}
        return value
    except (ValueError, TypeError, KeyError, RunnerError):
        raise RunnerError('UNCONFIRMED') from None
