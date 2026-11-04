import json
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from app.schemas.guest_runner import RunnerError
from app.schemas.iaas_access import PROTOCOL, parse_request


def _clave():
    publica = ed25519.Ed25519PrivateKey.generate().public_key()
    return publica.public_bytes(serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH).decode() + ' comentario'


def _base(**cambios):
    valor = {'protocol': PROTOCOL, 'operation_id': str(uuid4()), 'action': 'configure', 'cluster_uuid': str(uuid4()),
        'resource_uuid': str(uuid4()), 'node': 'pve91', 'vmid': 101, 'pool': 'catedra-3', 'nonce': 'n' * 30,
        'revision': 1, 'usuario': 'nap', 'clave_publica': _clave()}
    valor.update(cambios)
    return valor


def _raw(valor):
    return json.dumps(valor).encode()


def test_configure_normaliza_la_clave_y_agrega_la_huella():
    parsed = parse_request(_raw(_base()))
    assert ' ' not in parsed['clave_publica'].split(' ', 1)[1]  # sin comentario
    assert parsed['huella'].startswith('SHA256:')


def test_probe_exige_huella_y_no_acepta_clave():
    huella = parse_request(_raw(_base()))['huella']
    probe = {k: v for k, v in _base(action='probe', huella=huella).items() if k != 'clave_publica'}
    assert parse_request(_raw(probe))['action'] == 'probe'
    with pytest.raises(RunnerError):
        parse_request(_raw(_base(action='probe', huella=huella)))  # trae clave_publica de más


@pytest.mark.parametrize('cambios', [
    {'protocol': 'nap-guest-runner/1'}, {'action': 'bootstrap'}, {'usuario': 'root'}, {'usuario': 'nap2'},
    {'vmid': 99}, {'vmid': '101'}, {'revision': 0}, {'revision': True}, {'node': '../x'}, {'pool': 'a b'},
    {'nonce': 'corto'}, {'operation_id': 'no-uuid'}, {'clave_publica': 'ssh-ed25519 AAAA'},
    {'clave_publica': '-----BEGIN OPENSSH PRIVATE KEY-----'},
])
def test_rechaza_valores_invalidos(cambios):
    with pytest.raises(RunnerError) as exc:
        parse_request(_raw(_base(**cambios)))
    assert exc.value.code == 'INVALID_REQUEST'


def test_rechaza_campos_extra_o_faltantes():
    extra = _base(); extra['otro'] = 1
    faltante = _base(); del faltante['pool']
    for valor in (extra, faltante):
        with pytest.raises(RunnerError):
            parse_request(_raw(valor))


def test_rechaza_claves_duplicadas_y_exceso_de_tamano():
    crudo = _raw(_base()).replace(b'"vmid": 101', b'"vmid": 101, "vmid": 102')
    with pytest.raises(RunnerError):
        parse_request(crudo)
    with pytest.raises(RunnerError):
        parse_request(b'{' + b' ' * 20000 + b'}')


def test_rechaza_entrada_no_bytes():
    with pytest.raises(RunnerError):
        parse_request('{}')


def test_la_respuesta_acepta_una_direccion_ipv4_y_rechaza_cualquier_otra_cosa():
    from app.schemas.iaas_access import parse_response
    pedido = _base(action='probe', huella='SHA256:' + 'A' * 43)
    pedido.pop('clave_publica')
    def respuesta(direccion):
        return json.dumps({'protocol': PROTOCOL, 'operation_id': pedido['operation_id'], 'action': 'probe',
            'resource_uuid': pedido['resource_uuid'], 'status': 'succeeded', 'identity_verified': True,
            'result': {'ready': True, 'revision': 1, 'huella': pedido['huella'], 'usuario': 'nap', 'puerto': 22, 'direccion': direccion}}).encode()
    assert parse_response(respuesta('192.168.100.18'), pedido)['result']['direccion'] == '192.168.100.18'
    for malo in ['no-es-ip', '999.1.1.1', 5, None, '::1', '1.2.3.4; rm -rf /']:
        with pytest.raises(RunnerError):
            parse_response(respuesta(malo), pedido)
