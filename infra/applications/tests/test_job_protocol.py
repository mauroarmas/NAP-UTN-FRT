"""Protocolo cerrado: identidad completa y fingerprints sin valores secretos."""
from copy import deepcopy
from hashlib import sha256
import json
from uuid import uuid4

import pytest

from infra.applications.job.protocol import JobError, parse_request, parse_response, fingerprint


@pytest.fixture
def request_identity():
    return {'protocol': 'nap-application-job/1', 'action': 'status',
            **{key: str(uuid4()) for key in ('operation_id', 'operacion_raiz_id', 'intento_id',
                 'execution_id', 'cluster_uuid', 'resource_uuid')},
            'lease_generation': 1, 'node': 'proxmox', 'vmid': 900011, 'pool': 'nap-apps',
            'nonce': 'e' * 64, 'configuracion_sha256': 'c' * 64,
            'perfil': {'id': 'docker-ubuntu24', 'revision': 1, 'sha256': 'a' * 64}}


def wire(value):
    return json.dumps(value).encode()


def test_actions_and_bounded_cursors(request_identity):
    assert parse_request(wire(request_identity)) == request_identity
    for action, extra in [('read', {'after': 0, 'limit_bytes': 65536}), ('ack', {'through_seq': 4})]:
        value = {**request_identity, 'action': action, **extra}
        assert parse_request(wire(value)) == value
    assert parse_request(b'{"protocol":"nap-application-job/1","action":"profiles"}')['action'] == 'profiles'


@pytest.mark.parametrize('key,value', [('command', 'id'), ('argv', ['sh']), ('path', '/etc/passwd'),
    ('unit', 'ssh.service'), ('url', 'https://untrusted/install.sh'), ('shell', True),
    ('vmid', True), ('lease_generation', 0), ('vmid', 99), ('node', '../proxmox'),
    ('pool', 'a/b'), ('nonce', 'too-short'), ('execution_id', 'not-a-uuid')])
def test_reject_unsafe_request_without_echoing_values(request_identity, key, value):
    request_identity[key] = value
    with pytest.raises(JobError) as caught: parse_request(wire(request_identity))
    assert caught.value.code == 'INVALID_REQUEST'
    assert str(value) not in str(caught.value)


def test_action_specific_shape_and_duplicate_keys(request_identity):
    for extra in [{'after': 0}, {'secretos': {}}, {'through_seq': 1}]:
        with pytest.raises(JobError): parse_request(wire({**request_identity, **extra}))
    for raw in [wire(request_identity)[:-1] + b',"action":"start"}', b'[]',
                b'{"value":NaN}', wire({**request_identity, 'lease_generation': 1.0}), b'x' * 1048577]:
        with pytest.raises(JobError): parse_request(raw)


def test_fingerprint_excludes_transport_generation_and_values_but_binds_references(request_identity):
    request_identity.update(action='start', configuracion={'test': 'public-fixture'},
                            secretos={'APP_PASSWORD': 'fixture-private-value'},
                            secreto_referencias=[{'id': str(uuid4()), 'nombre': 'APP_PASSWORD', 'revision': 1}])
    # Fingerprint only hashes public content; start parsing separately validates its schema.
    first = fingerprint(request_identity)
    changed = deepcopy(request_identity)
    changed['lease_generation'] = 2
    changed['secretos']['APP_PASSWORD'] = 'different-private-value'
    assert fingerprint(changed) == first
    changed['secreto_referencias'][0]['revision'] = 2
    assert fingerprint(changed) != first
    for key in ['execution_id', 'resource_uuid', 'intento_id']:
        changed = deepcopy(request_identity); changed[key] = str(uuid4())
        assert fingerprint(changed) != first


def test_closed_error_codes():
    assert str(JobError('IDENTITY_MISMATCH')) == 'IDENTITY_MISMATCH'
    assert JobError('an accidental exception with credentials').code == 'UNCONFIRMED'


def status_response(request):
    return {'protocol': 'nap-application-job/1', 'ok': True, 'action': 'status', 'data': {
        **{k: v for k, v in request.items() if k not in {'protocol', 'action', 'nonce'}},
        'nonce_sha256': sha256(request['nonce'].encode()).hexdigest(),
        'estado': 'ejecutando', 'fase': 'instalacion', 'fingerprint': 'f'*64,
        'node_boot_id': str(uuid4()), 'last_source_seq': 2, 'acknowledged_seq': 0,
        'resultado': None, 'error_codigo': None}}


def test_status_response_has_complete_identity_and_closed_safe_result(request_identity):
    value = status_response(request_identity)
    assert parse_response(wire(value), request=request_identity) == value
    assert request_identity['nonce'] not in wire(value).decode()
    for mutation in ['identity', 'secret', 'error', 'boolean', 'phase', 'result']:
        changed = deepcopy(value)
        if mutation == 'identity': changed['data']['resource_uuid'] = str(uuid4())
        if mutation == 'secret': changed['data']['password'] = 'never-echo-this'
        if mutation == 'error': changed['data']['error_codigo'] = 'trace contains never-echo-this'
        if mutation == 'boolean': changed['data']['last_source_seq'] = True
        if mutation == 'phase': changed['data']['fase'] = 'unsafe-free-output'
        if mutation == 'result': changed['data']['resultado'] = {'stdout': 'never-echo-this'}
        with pytest.raises(JobError) as caught: parse_response(wire(changed), request=request_identity)
        assert 'never-echo-this' not in str(caught.value)


def test_response_error_code_and_read_cursor_bounds(request_identity):
    assert parse_response(b'{"protocol":"nap-application-job/1","ok":false,"error":"NO_SPACE"}',
                          request=request_identity)['error'] == 'NO_SPACE'
    with pytest.raises(JobError):
        parse_response(b'{"protocol":"nap-application-job/1","ok":false,"error":"unknown"}', request=request_identity)
    request_identity.update(action='read', after=0, limit_bytes=65536)
    response = status_response(request_identity)
    response['action'] = 'read'
    for key in ['after', 'limit_bytes']: response['data'].pop(key)
    response['data'].update(items=[{'execution_id': request_identity['execution_id'], 'source_seq': 1,
        'captured_at': '2026-10-26T13:00:00Z', 'fase': 'instalacion', 'stream': 'stdout', 'texto_depurado': 'Instalando…'}], dropped_ranges=[])
    assert parse_response(wire(response), request=request_identity)['data']['items'][0]['source_seq'] == 1
    for text in ['x'*8193, '\x1b[31munsafe', 'a\x00b']:
        response['data']['items'][0]['texto_depurado'] = text
        with pytest.raises(JobError): parse_response(wire(response), request=request_identity)


def test_cleanup_is_closed_identity_bound_and_never_accepts_guest_commands():
    from uuid import uuid4
    from infra.applications.job.protocol import parse_request,parse_response,canonical,fingerprint,JobError,PROTOCOL
    request={'protocol':PROTOCOL,'action':'cleanup','cluster_uuid':str(uuid4()),'resource_uuid':str(uuid4()),
        'node':'proxmox','vmid':101,'nonce':'a'*64}
    assert parse_request(canonical(request))==request
    reply={'protocol':PROTOCOL,'ok':True,'action':'cleanup','data':{'released':True,'fingerprint':fingerprint(request)}}
    assert parse_response(canonical(reply),request=request)==reply
    with pytest.raises(JobError):parse_request(canonical(request|{'command':'nft flush ruleset'}))
    with pytest.raises(JobError):parse_response(canonical(reply),request=request|{'nonce':'b'*64})
