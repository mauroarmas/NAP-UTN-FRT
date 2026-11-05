import json
from uuid import uuid4

import pytest

from app.schemas.console_identity import PROTOCOL, parse_request, parse_response
from app.schemas.guest_runner import RunnerError

PW = 'Xk3_' + 'a1B2c3D4' * 4


def base(action='ensure', **cambios):
    valor = {'protocol': PROTOCOL, 'operation_id': str(uuid4()), 'action': action, 'cluster_uuid': str(uuid4()),
        'identidad': 'nap-u12@pve', 'revision': 1}
    if action == 'ensure':
        valor.update(password_consola=PW, pools=['catedra-3'])
    if action == 'end_sessions':
        valor.update(vmids=[101])
    valor.update(cambios)
    return valor


def raw(valor):
    return json.dumps(valor).encode()


@pytest.mark.parametrize('action', ['ensure', 'retire', 'end_sessions', 'probe'])
def test_cada_accion_valida_se_acepta(action):
    assert parse_request(raw(base(action)))['action'] == action


def test_retire_acepta_pools_opcionales():
    assert 'pools' not in parse_request(raw(base('retire')))
    assert parse_request(raw(base('retire', pools=['catedra-3'])))['pools'] == ['catedra-3']


@pytest.mark.parametrize('identidad', ['root@pam', 'nap-u1@pam', 'nap-u@pve', 'nap-ux@pve', 'otro@pve', 'nap-u1@pve ', '',
    'nap-u1@pve\n', None, 7, 'nap-u1234567890123@pve'])
def test_rechaza_identidades_fuera_del_patron(identidad):
    with pytest.raises(RunnerError) as exc:
        parse_request(raw(base(identidad=identidad)))
    assert exc.value.code == 'INVALID_REQUEST'


@pytest.mark.parametrize('cambios', [
    {'pools': ['catedra-3', 'catedra-3']}, {'pools': ['pool-1']}, {'pools': ['catedra-3; rm']}, {'pools': 'catedra-3'},
    {'pools': ['catedra-%d' % n for n in range(201)]}, {'password_consola': 'corta'}, {'password_consola': PW + ' '},
    {'password_consola': None}, {'revision': 0}, {'revision': True}, {'operation_id': 'x'}, {'extra': 1},
])
def test_ensure_rechaza_valores_invalidos(cambios):
    with pytest.raises(RunnerError):
        parse_request(raw(base(**cambios)))


@pytest.mark.parametrize('vmids', [[], [99], [101, 101], ['101'], [True], [10**10], list(range(100, 301))])
def test_end_sessions_rechaza_vmids_invalidos(vmids):
    with pytest.raises(RunnerError):
        parse_request(raw(base('end_sessions', vmids=vmids)))


def test_rechaza_campos_cruzados_entre_acciones():
    with pytest.raises(RunnerError):
        parse_request(raw(base('probe', password_consola=PW)))
    with pytest.raises(RunnerError):
        parse_request(raw(base('retire', password_consola=PW)))
    with pytest.raises(RunnerError):
        parse_request(raw({k: v for k, v in base().items() if k != 'password_consola'}))


def test_rechaza_entrada_que_no_son_bytes_o_excede_el_tamano():
    with pytest.raises(RunnerError):
        parse_request(json.dumps(base()))
    with pytest.raises(RunnerError):
        parse_request(raw(base()) + b' ' * 70000)


def respuesta(request, **cambios):
    valor = {'protocol': PROTOCOL, 'operation_id': request['operation_id'], 'action': request['action'],
        'identidad': request['identidad'], 'status': 'succeeded', 'phase': 'verified', 'identity_verified': True,
        'observed_at': '2026-11-04T00:00:00+00:00',
        'result': {'pools_aplicados': ['catedra-3'], 'pools_pendientes': [], 'creada': True, 'password': 'aplicada'}}
    valor.update(cambios)
    return raw(valor)


def test_la_respuesta_correcta_se_acepta():
    pedido = parse_request(raw(base()))
    assert parse_response(respuesta(pedido), pedido)['status'] == 'succeeded'


@pytest.mark.parametrize('cambios', [
    {'operation_id': str(uuid4())}, {'identidad': 'nap-u99@pve'}, {'action': 'probe'}, {'identity_verified': False},
    {'result': {'password': 'texto'}}, {'result': {'pools_aplicados': ['x']}}, {'result': {'otra': 1}},
    {'status': 'raro'}, {'protocolo_extra': 1},
])
def test_respuestas_incoherentes_se_tratan_como_sin_confirmar(cambios):
    pedido = parse_request(raw(base()))
    with pytest.raises(RunnerError) as exc:
        parse_response(respuesta(pedido, **cambios), pedido)
    assert exc.value.code == 'UNCONFIRMED'


def test_un_codigo_de_error_desconocido_se_trata_como_reintentable():
    pedido = parse_request(raw(base()))
    valor = json.loads(respuesta(pedido)); valor.pop('result'); valor.update(status='failed', error={'code': 'RARO'})
    resp = parse_response(raw(valor), pedido)
    assert resp['error'] == {'code': 'UNCONFIRMED', 'retryable': True}
