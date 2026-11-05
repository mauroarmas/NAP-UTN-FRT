"""Transporte del protocolo nap-iaas-access/1: SSH fijo, clave solo por stdin, respuesta acotada."""
import json
from uuid import uuid4

import pytest

from app.schemas.guest_runner import RunnerError
from tests.iaas_ssh_helpers import nueva_clave
from tests.test_guest_runner_client import runner_config  # noqa: F401


def pedido(**cambios):
    valor = {'protocol': 'nap-iaas-access/1', 'operation_id': str(uuid4()), 'action': 'configure', 'cluster_uuid': str(uuid4()),
        'resource_uuid': str(uuid4()), 'node': 'pve1', 'vmid': 101, 'pool': 'catedra-1', 'nonce': 'n' * 43,
        'revision': 1, 'usuario': 'nap', 'clave_publica': nueva_clave()}
    return valor | cambios


def proceso(respuesta, capturado, codigo=0):
    class Proceso:
        returncode = codigo
        async def communicate(self, input=None):
            capturado['input'] = input
            return (respuesta(json.loads(input)) if callable(respuesta) else respuesta), b''
    async def iniciar(*args, **kwargs):
        capturado['argv'] = args
        return Proceso()
    return iniciar


def ok(valor):
    return json.dumps({'protocol': valor['protocol'], 'operation_id': valor['operation_id'], 'action': valor['action'],
        'resource_uuid': valor['resource_uuid'], 'status': 'succeeded', 'phase': 'verified', 'identity_verified': True,
        'observed_at': '2026-11-03T00:00:00+00:00',
        'result': {'ready': True, 'revision': valor['revision'], 'huella': 'SHA256:' + 'A' * 43, 'usuario': 'nap', 'puerto': 22}}).encode()


async def test_la_clave_viaja_por_stdin_y_no_por_argumentos(runner_config, caplog):
    from app.services.guest_runner_client import GuestRunnerClient
    valor, capturado = pedido(), {}
    respuesta = await GuestRunnerClient(config=runner_config, start_process=proceso(ok, capturado)).execute_iaas_access(valor)
    assert respuesta['status'] == 'succeeded'
    cuerpo = valor['clave_publica'].split()[1]
    assert cuerpo not in repr(capturado['argv']) + caplog.text
    assert cuerpo.encode() in capturado['input']
    args = capturado['argv']
    assert 'StrictHostKeyChecking=yes' in args and 'PasswordAuthentication=no' in args and args[-1] == 'nap-guest-runner'


@pytest.mark.parametrize('cambios', [{'usuario': 'root'}, {'action': 'bootstrap'}, {'clave_publica': 'no es una clave'}, {'extra': 1}])
async def test_solicitud_invalida_no_sale_al_nodo(runner_config, cambios):
    from app.services.guest_runner_client import GuestRunnerClient
    capturado = {}
    with pytest.raises(RunnerError) as exc:
        await GuestRunnerClient(config=runner_config, start_process=proceso(ok, capturado)).execute_iaas_access(pedido(**cambios))
    assert exc.value.code == 'INVALID_REQUEST' and 'argv' not in capturado


async def test_respuesta_de_otra_operacion_se_rechaza(runner_config):
    from app.services.guest_runner_client import GuestRunnerClient
    ajena = lambda v: ok(v | {'operation_id': str(uuid4())})
    with pytest.raises(RunnerError) as exc:
        await GuestRunnerClient(config=runner_config, start_process=proceso(ajena, {})).execute_iaas_access(pedido())
    assert exc.value.code == 'UNCONFIRMED'


async def test_codigo_de_error_desconocido_se_trata_como_sin_confirmar(runner_config):
    from app.services.guest_runner_client import GuestRunnerClient
    def raro(v):
        return json.dumps({'protocol': v['protocol'], 'operation_id': v['operation_id'], 'action': v['action'],
            'resource_uuid': v['resource_uuid'], 'status': 'failed', 'error': {'code': 'SECRETO_QUE_NO_DEBE_VERSE'}}).encode()
    respuesta = await GuestRunnerClient(config=runner_config, start_process=proceso(raro, {})).execute_iaas_access(pedido())
    assert respuesta['error'] == {'code': 'UNCONFIRMED', 'retryable': True}


async def test_salida_del_ssh_con_error_es_runner_no_disponible(runner_config):
    from app.services.guest_runner_client import GuestRunnerClient
    with pytest.raises(RunnerError) as exc:
        await GuestRunnerClient(config=runner_config, start_process=proceso(b'', {}, codigo=255)).execute_iaas_access(pedido())
    assert exc.value.code == 'RUNNER_UNAVAILABLE'
