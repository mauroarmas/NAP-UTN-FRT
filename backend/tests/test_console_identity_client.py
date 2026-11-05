"""Transporte del protocolo nap-console-identity/1: SSH fijo, contraseña sólo por stdin, respuesta acotada."""
import json
from uuid import uuid4

import pytest

from app.schemas.guest_runner import RunnerError
from tests.test_guest_runner_client import runner_config  # noqa: F401

PW = 'Xk3_' + 'a1B2c3D4' * 4


def pedido(**cambios):
    valor = {'protocol': 'nap-console-identity/1', 'operation_id': str(uuid4()), 'action': 'ensure', 'cluster_uuid': str(uuid4()),
        'identidad': 'nap-u12@pve', 'revision': 1, 'password_consola': PW, 'pools': ['catedra-3']}
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
        'identidad': valor['identidad'], 'status': 'succeeded', 'phase': 'verified', 'identity_verified': True,
        'observed_at': '2026-11-04T00:00:00+00:00',
        'result': {'pools_aplicados': ['catedra-3'], 'pools_pendientes': [], 'creada': True, 'password': 'aplicada'}}).encode()


async def test_la_contrasena_viaja_por_stdin_y_no_por_argumentos(runner_config, caplog):
    from app.services.guest_runner_client import GuestRunnerClient
    capturado = {}
    respuesta = await GuestRunnerClient(config=runner_config, start_process=proceso(ok, capturado)).execute_console_identity(pedido(), 'pve1')
    assert respuesta['status'] == 'succeeded'
    assert PW not in repr(capturado['argv']) + caplog.text and PW.encode() in capturado['input']
    args = capturado['argv']
    assert 'StrictHostKeyChecking=yes' in args and 'PasswordAuthentication=no' in args and args[-1] == 'nap-guest-runner'


@pytest.mark.parametrize('cambios', [{'identidad': 'root@pam'}, {'action': 'bootstrap'}, {'pools': ['/']}, {'extra': 1}, {'password_consola': 'corta'}])
async def test_solicitud_invalida_no_sale_al_nodo(runner_config, cambios):
    from app.services.guest_runner_client import GuestRunnerClient
    capturado = {}
    with pytest.raises(RunnerError) as exc:
        await GuestRunnerClient(config=runner_config, start_process=proceso(ok, capturado)).execute_console_identity(pedido(**cambios), 'pve1')
    assert exc.value.code == 'INVALID_REQUEST' and 'argv' not in capturado


async def test_un_nodo_desconocido_no_ejecuta_nada(runner_config):
    from app.services.guest_runner_client import GuestRunnerClient
    capturado = {}
    with pytest.raises(Exception):
        await GuestRunnerClient(config=runner_config, start_process=proceso(ok, capturado)).execute_console_identity(pedido(), 'inventado')
    assert 'argv' not in capturado


async def test_respuesta_de_otra_operacion_o_identidad_se_rechaza(runner_config):
    from app.services.guest_runner_client import GuestRunnerClient
    for cambio in ({'operation_id': str(uuid4())}, {'identidad': 'nap-u99@pve'}):
        def otra(valor, cambio=cambio):
            return json.dumps(json.loads(ok(valor)) | cambio).encode()
        with pytest.raises(RunnerError) as exc:
            await GuestRunnerClient(config=runner_config, start_process=proceso(otra, {})).execute_console_identity(pedido(), 'pve1')
        assert exc.value.code == 'UNCONFIRMED'


async def test_salida_con_codigo_distinto_de_cero_es_runner_no_disponible(runner_config):
    from app.services.guest_runner_client import GuestRunnerClient
    with pytest.raises(RunnerError) as exc:
        await GuestRunnerClient(config=runner_config, start_process=proceso(ok, {}, codigo=255)).execute_console_identity(pedido(), 'pve1')
    assert exc.value.code == 'RUNNER_UNAVAILABLE'


async def test_respuesta_excesiva_se_corta(runner_config):
    from app.services.guest_runner_client import GuestRunnerClient
    with pytest.raises(RunnerError):
        await GuestRunnerClient(config=runner_config, start_process=proceso(b'x' * 70000, {})).execute_console_identity(pedido(), 'pve1')
