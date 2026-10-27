"""Wire protocol for the forced SSH dispatcher. No caller-selected executable.

Only start carries private values. Fingerprints bind public decisions and secret
references, never password hashes. Identity checks and fencing belong to admission.
"""
from hashlib import sha256
from datetime import datetime
import json
import re
from uuid import UUID


PROTOCOL = 'nap-application-job/1'
MAX_REQUEST_BYTES = 1048576
MAX_READ_BYTES = 65536
MAX_FRAGMENT_BYTES = 8192
MAX_RESPONSE_BYTES = 131072
PHASES = frozenset({'preparacion', 'creacion', 'entorno', 'instalacion', 'configuracion',
                    'arranque', 'comprobacion', 'finalizada'})
JOB_STATES = frozenset({'preparado', 'ejecutando', 'confirmado', 'fallido', 'incierto'})
ERROR_CODES = frozenset({'INVALID_REQUEST', 'PROFILE_UNAVAILABLE', 'IDENTITY_MISMATCH',
    'STALE_CONTROLLER', 'EXECUTION_CONFLICT', 'DEPENDENCY_UNAVAILABLE', 'NO_SPACE',
    'DEADLINE_EXCEEDED', 'UNCONFIRMED'})
IDENTITY_FIELDS = frozenset({'protocol', 'operation_id', 'operacion_raiz_id', 'intento_id',
    'execution_id', 'lease_generation', 'cluster_uuid', 'node', 'vmid', 'resource_uuid',
    'pool', 'nonce', 'configuracion_sha256', 'perfil'})
UUID_FIELDS = ('operation_id', 'operacion_raiz_id', 'intento_id', 'execution_id',
               'cluster_uuid', 'resource_uuid')


class JobError(Exception):
    def __init__(self, code):
        self.code = code if code in ERROR_CODES else 'UNCONFIRMED'
        super().__init__(self.code)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
                      allow_nan=False).encode('utf-8')


def strict_json(raw, *, limit=MAX_REQUEST_BYTES):
    def unique(items):
        result = {}
        for key, value in items:
            if key in result: raise ValueError()
            result[key] = value
        return result
    def invalid(_): raise ValueError()
    try:
        if type(raw) is not bytes or len(raw) > limit: raise ValueError()
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=unique,
                           parse_float=invalid, parse_constant=invalid)
        if type(value) is not dict: raise ValueError()
        return value
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise JobError('INVALID_REQUEST') from None


def _integer(value, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum: raise ValueError()


def _uuid(value):
    if type(value) is not str or str(UUID(value)) != value: raise ValueError()


def _match(pattern, value):
    if type(value) is not str or not re.fullmatch(pattern, value): raise ValueError()


def validate_profile(value):
    if type(value) is not dict or set(value) != {'id', 'revision', 'sha256'}: raise ValueError()
    _match(r'[a-z][a-z0-9-]{0,63}', value['id'])
    _integer(value['revision'], 1, 2**31-1)
    _match(r'[a-f0-9]{64}', value['sha256'])


def parse_request(raw):
    value = strict_json(raw)
    try:
        if value.get('protocol') != PROTOCOL: raise ValueError()
        action = value.get('action')
        if action == 'profiles':
            if set(value) != {'protocol', 'action'}: raise ValueError()
            return value
        extras = {'status': set(), 'start': {'configuracion', 'secretos', 'secreto_referencias'},
                  'read': {'after', 'limit_bytes'}, 'ack': {'through_seq'}}
        if type(action) is not str or action not in extras or set(value) != IDENTITY_FIELDS | {'action'} | extras[action]:
            raise ValueError()
        for key in UUID_FIELDS: _uuid(value[key])
        _integer(value['lease_generation'], 1, 2**63-1)
        _integer(value['vmid'], 100, 999999999)
        _match(r'[A-Za-z0-9][A-Za-z0-9._-]{0,99}', value['node'])
        _match(r'[A-Za-z0-9][A-Za-z0-9._-]{0,99}', value['pool'])
        for key in ('nonce', 'configuracion_sha256'): _match(r'[a-f0-9]{64}', value[key])
        validate_profile(value['perfil'])
        if action == 'read':
            _integer(value['after'], 0, 2**63-1)
            _integer(value['limit_bytes'], 1, MAX_READ_BYTES)
        if action == 'ack': _integer(value['through_seq'], 0, 2**63-1)
        if action == 'start':
            from .configuration import validate_configuration
            configuration = validate_configuration(value['configuracion'])
            if (configuration != value['configuracion'] or configuration['perfil'] != value['perfil']
                    or sha256(canonical(configuration)).hexdigest() != value['configuracion_sha256']):
                raise ValueError()
            secrets, refs = value['secretos'], value['secreto_referencias']
            declared = {s['nombre'] for s in configuration['secretos']}
            if type(secrets) is not dict or set(secrets) != declared or type(refs) is not list or len(refs) != len(declared):
                raise ValueError()
            for name, secret in secrets.items():
                if type(secret) is not str or not secret or '\x00' in secret or len(secret.encode('utf-8')) > 4096: raise ValueError()
            ref_names, ref_ids = set(), set()
            for ref in refs:
                if type(ref) is not dict or set(ref) != {'id', 'nombre', 'revision'}: raise ValueError()
                _uuid(ref['id']); _integer(ref['revision'], 1, 2**31-1)
                if ref['nombre'] not in declared or ref['nombre'] in ref_names or ref['id'] in ref_ids: raise ValueError()
                ref_names.add(ref['nombre']); ref_ids.add(ref['id'])
        return value
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        raise JobError('INVALID_REQUEST') from None


def fingerprint(request):
    public = {k: v for k, v in request.items() if k not in {'action', 'lease_generation', 'secretos'}}
    if 'nonce' in public:
        public['nonce_sha256'] = sha256(public.pop('nonce').encode('utf-8')).hexdigest()
    # Secret reference order is not an execution difference.
    if 'secreto_referencias' in public:
        public['secreto_referencias'] = sorted(public['secreto_referencias'], key=lambda ref: ref['nombre'])
    return sha256(canonical(public)).hexdigest()


def public_identity(request):
    """Proof of ownership is accepted privately, never echoed in status or state."""
    result = {k: request[k] for k in IDENTITY_FIELDS - {'protocol', 'nonce'}}
    result['nonce_sha256'] = sha256(request['nonce'].encode('utf-8')).hexdigest()
    return json.loads(canonical(result))


def _keys(value, expected):
    if type(value) is not dict or set(value) != expected: raise ValueError()


def _timestamp(value):
    if type(value) is not str or not value.endswith('Z') or len(value) > 32: raise ValueError()
    datetime.fromisoformat(value[:-1] + '+00:00')


def parse_response(raw, *, request):
    """El cliente valida identidad y límites antes de almacenar/confirmar un cursor."""
    value = strict_json(raw, limit=MAX_RESPONSE_BYTES)
    try:
        if value.get('protocol') != PROTOCOL or type(value.get('ok')) is not bool: raise ValueError()
        if value['ok'] is False:
            _keys(value, {'protocol', 'ok', 'error'})
            if value['error'] not in ERROR_CODES: raise ValueError()
            return value
        _keys(value, {'protocol', 'ok', 'action', 'data'})
        if value['action'] != request['action']: raise ValueError()
        action, data = value['action'], value['data']
        if action == 'profiles':
            _keys(data, {'profiles'})
            profiles = data['profiles']
            if type(profiles) is not list or len(profiles) > 200: raise ValueError()
            seen = set()
            for profile in profiles:
                _keys(profile, {'id', 'revision', 'sha256', 'estado', 'motivo_codigo'})
                validate_profile({k: profile[k] for k in ('id', 'revision', 'sha256')})
                if profile['estado'] not in {'pendiente_validacion', 'habilitado', 'bloqueado'}: raise ValueError()
                if profile['estado'] == 'habilitado':
                    if profile['motivo_codigo'] is not None: raise ValueError()
                elif profile['motivo_codigo'] not in {'VALIDATION_REQUIRED', 'PLATFORM_CHANGED',
                        'DEPENDENCY_UNAVAILABLE', 'ISOLATION_FAILED', 'RESOURCE_LIMIT', 'ADMIN_BLOCKED'}: raise ValueError()
                pair = (profile['id'], profile['revision'])
                if pair in seen: raise ValueError()
                seen.add(pair)
            return value
        expected_identity = public_identity(request)
        identity = set(expected_identity)
        extra = {'items', 'dropped_ranges'} if action == 'read' else set()
        _keys(data, identity | {'estado', 'fase', 'fingerprint', 'node_boot_id',
              'last_source_seq', 'acknowledged_seq', 'resultado', 'error_codigo'} | extra)
        if action not in {'start', 'status', 'read', 'ack'}: raise ValueError()
        if any(data[k] != expected_identity[k] or type(data[k]) is not type(expected_identity[k]) for k in identity): raise ValueError()
        if data['estado'] not in JOB_STATES or data['fase'] not in PHASES: raise ValueError()
        _uuid(data['node_boot_id']); _match(r'[a-f0-9]{64}', data['fingerprint'])
        _integer(data['last_source_seq'], 0, 2**63-1)
        _integer(data['acknowledged_seq'], 0, data['last_source_seq'])
        if action == 'ack' and data['acknowledged_seq'] < request['through_seq']: raise ValueError()
        if data['error_codigo'] is not None and data['error_codigo'] not in ERROR_CODES: raise ValueError()
        result = data['resultado']
        if result is not None:
            _keys(result, {'comprobaciones', 'recurso_configurado'})
            if type(result['recurso_configurado']) is not bool or type(result['comprobaciones']) is not list: raise ValueError()
            allowed = {'runtime', 'aislamiento', 'salud', 'acceso_web', 'autenticacion_tcp'}
            if (len(result['comprobaciones']) > len(allowed) or len(set(result['comprobaciones'])) != len(result['comprobaciones'])
                    or set(result['comprobaciones']) - allowed): raise ValueError()
        if action == 'read':
            items, ranges = data['items'], data['dropped_ranges']
            if type(items) is not list or len(items) > 1000 or len(canonical(items)) > request['limit_bytes']: raise ValueError()
            previous = request['after']
            for item in items:
                _keys(item, {'execution_id', 'source_seq', 'captured_at', 'fase', 'stream', 'texto_depurado'})
                if item['execution_id'] != request['execution_id']: raise ValueError()
                _integer(item['source_seq'], max(previous, data['acknowledged_seq']) + 1, data['last_source_seq'])
                previous = item['source_seq']; _timestamp(item['captured_at'])
                if item['fase'] not in PHASES or item['stream'] not in {'sistema', 'stdout', 'stderr'}: raise ValueError()
                text = item['texto_depurado']
                if (type(text) is not str or not 1 <= len(text.encode('utf-8')) <= MAX_FRAGMENT_BYTES
                        or any(ord(c) < 32 and c not in '\n\t' or 127 <= ord(c) <= 159 for c in text)): raise ValueError()
            if type(ranges) is not list or len(ranges) > 1000: raise ValueError()
            previous = 0
            for lost in ranges:
                _keys(lost, {'from_seq', 'through_seq', 'bytes'})
                _integer(lost['from_seq'], previous+1, data['last_source_seq'])
                _integer(lost['through_seq'], lost['from_seq'], data['last_source_seq'])
                _integer(lost['bytes'], 0, 2**63-1); previous = lost['through_seq']
        return value
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        raise JobError('INVALID_REQUEST') from None
