"""Protocolo cerrado de biblioteca estándar; se instala igual en el nodo."""
from datetime import datetime
import ipaddress
import json
import re
from urllib.parse import urlsplit
from uuid import UUID


PROTOCOL = 'nap-guest-runner/1'
FIELDS = {'protocol', 'operation_id', 'action', 'cluster_uuid', 'resource_uuid', 'node', 'vmid', 'pool',
    'nonce', 'definition_key', 'definition_version', 'definition_sha256', 'bundle_sha256', 'network_profile_id', 'parameters'}
IDENTITY_FIELDS = ['cluster_uuid', 'resource_uuid', 'node', 'vmid', 'pool', 'nonce', 'definition_sha256', 'bundle_sha256']
RESULT_FIELDS = {'ready', 'bootstrap_completed', 'host', 'address', 'addresses', 'endpoint', 'port',
    'username', 'database', 'checks', 'version', 'definition_sha256', 'bundle_sha256'}
SECRET_SETS = [{'guest_password'}, {'database_password'}, {'teacher_password', 'database_password', 'app_key'}]
PRODUCT_PARAMETERS = {'linux': {'display_name'}, 'postgresql': {'display_name', 'database_name'},
    'bookstack': {'display_name', 'teacher_name', 'teacher_email', 'locale'}}


class RunnerError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def parse_json(raw, *, limit=65536):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError()
            result[key] = value
        return result
    def invalid(value):
        raise ValueError()
    try:
        if not isinstance(raw, bytes) or len(raw) > limit:
            raise ValueError()
        return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_float=invalid, parse_constant=invalid)
    except (ValueError, TypeError, RecursionError):
        raise RunnerError('INVALID_REQUEST') from None


def _uuid(value):
    return isinstance(value, str) and str(UUID(value)) == value


def parse_request(raw):
    value = parse_json(raw)
    try:
        if not isinstance(value, dict) or not FIELDS <= set(value) or not set(value) <= FIELDS | {'secrets'}:
            raise ValueError()
        if value['protocol'] != PROTOCOL or value['action'] not in {'bootstrap', 'inspect', 'verify'}:
            raise ValueError()
        if not all(_uuid(value[key]) for key in ['operation_id', 'cluster_uuid', 'resource_uuid']):
            raise ValueError()
        if type(value['vmid']) is not int or not 100 <= value['vmid'] <= 999999999:
            raise ValueError()
        for key, pattern in {'node': r'[a-zA-Z0-9][a-zA-Z0-9-]{0,62}', 'pool': r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,99}',
            'definition_key': r'[a-z][a-z0-9-]{1,63}', 'definition_version': r'[0-9]+\.[0-9]+\.[0-9]+',
            'network_profile_id': r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,99}', 'nonce': r'[a-zA-Z0-9_-]{22,128}',
            'definition_sha256': r'[a-f0-9]{64}', 'bundle_sha256': r'[a-f0-9]{64}'}.items():
            if not isinstance(value[key], str) or not re.fullmatch(pattern, value[key]):
                raise ValueError()
        parameters = value['parameters']
        if not isinstance(parameters, dict) or not set(parameters) <= set.union(*PRODUCT_PARAMETERS.values()):
            raise ValueError()
        if any(not isinstance(item, str) or not item.strip() or len(item) > (254 if key == 'teacher_email' else 100)
            or any(ord(char) < 32 for char in item) for key, item in parameters.items()):
            raise ValueError()
        if value['action'] == 'bootstrap':
            secrets = value.get('secrets')
            if not isinstance(secrets, dict) or set(secrets) not in SECRET_SETS or any(
                not isinstance(item, str) or not 1 <= len(item) <= 512 or any(ord(char) < 32 for char in item) for item in secrets.values()):
                raise ValueError()
        elif 'secrets' in value:
            raise ValueError()
        return value
    except (ValueError, TypeError, KeyError, AttributeError):
        raise RunnerError('INVALID_REQUEST') from None


def safe_result(value, request):
    try:
        if not isinstance(value, dict) or not set(value) <= RESULT_FIELDS:
            raise ValueError()
        if 'ready' in value and type(value['ready']) is not bool:
            raise ValueError()
        if 'bootstrap_completed' in value and type(value['bootstrap_completed']) is not bool:
            raise ValueError()
        if 'port' in value and (type(value['port']) is not int or not 1 <= value['port'] <= 65535):
            raise ValueError()
        for name in ['host', 'endpoint', 'username', 'database', 'version', 'definition_sha256', 'bundle_sha256']:
            if name in value and (not isinstance(value[name], str) or not 1 <= len(value[name]) <= 512
                or any(ord(char) < 32 for char in value[name])):
                raise ValueError()
        if 'address' in value:
            ipaddress.ip_address(value['address'])
        if 'addresses' in value:
            if not isinstance(value['addresses'], list) or len(value['addresses']) > 16:
                raise ValueError()
            for item in value['addresses']:
                ipaddress.ip_address(item)
        if 'checks' in value and (not isinstance(value['checks'], list) or len(value['checks']) > 16 or any(
            not isinstance(item, str) or not re.fullmatch(r'[a-z0-9-]{1,80}', item) for item in value['checks'])):
            raise ValueError()
        if 'endpoint' in value:
            url = urlsplit(value['endpoint'])
            if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in {'', '/'}:
                raise ValueError()
        encoded = canonical(value)
        if len(encoded.encode()) > 16384 or any(secret in encoded for secret in [request['nonce'], *request.get('secrets', {}).values()]):
            raise ValueError()
        return value
    except (ValueError, TypeError, KeyError):
        raise RunnerError('UNCONFIRMED') from None


def parse_response(raw, request):
    value = parse_json(raw)
    try:
        fields = {'protocol', 'operation_id', 'action', 'resource_uuid', 'status', 'phase', 'observed_at', 'identity_verified'}
        if not isinstance(value, dict) or not fields <= set(value) or not set(value) <= fields | {'result', 'error'}:
            raise ValueError()
        if any(value[key] != request[key] for key in ['protocol', 'operation_id', 'action', 'resource_uuid']):
            raise ValueError()
        if value['status'] not in {'succeeded', 'pending', 'failed', 'unconfirmed'} or type(value['identity_verified']) is not bool:
            raise ValueError()
        if not isinstance(value['phase'], str) or not re.fullmatch(r'[a-z_]{1,40}', value['phase']):
            raise ValueError()
        observed = datetime.fromisoformat(value['observed_at'].replace('Z', '+00:00'))
        if observed.tzinfo is None:
            raise ValueError()
        if ('result' in value) == ('error' in value):
            raise ValueError()
        if 'result' in value:
            safe_result(value['result'], request)
        if 'error' in value:
            err = value['error']
            if not isinstance(err, dict) or set(err) != {'code', 'phase', 'retryable', 'message'} or type(err['retryable']) is not bool:
                raise ValueError()
            if not re.fullmatch(r'[A-Z_]{1,50}', err['code']) or err['phase'] != value['phase'] or err['message'] != 'Resultado no confirmado; revisar la operación':
                raise ValueError()
        if value['status'] == 'succeeded' and (not value['identity_verified'] or 'result' not in value or value['result'].get('ready') is not True):
            raise ValueError()
        return value
    except (ValueError, TypeError, KeyError, AttributeError):
        raise RunnerError('UNCONFIRMED') from None
