import json
from uuid import uuid4

import pytest

from app.schemas.biblioteca_config import BuilderHost
from app.schemas.guest_runner import RunnerError
from app.services.build_runner_client import BuildRunnerClient


@pytest.fixture
def builder_host(tmp_path):
    key, known = tmp_path / 'key', tmp_path / 'known_hosts'
    key.write_text('test-key-not-used'); key.chmod(0o600)
    known.write_text('builder.invalid ssh-ed25519 TEST-ONLY'); known.chmod(0o644)
    return BuilderHost(host='builder.invalid', user='nap-builder', port=2222,
        private_key_path=str(key), known_hosts_path=str(known), scope_id='scope-lab',
        limit_bytes=1024, job_bytes=512)


def status_request():
    return {'protocol': 'nap-build-runner/1', 'operation_id': str(uuid4()),
            'ensayo_id': str(uuid4()), 'generation': 1, 'action': 'status'}


@pytest.mark.parametrize('as_dict', [False, True])
async def test_configuracion_institucional_completa_llega_al_transporte_ssh(builder_host, as_dict):
    """Los campos de presupuesto no son opciones SSH ni invalidan el destino."""
    captured = {}
    request = status_request()
    class Process:
        returncode = 0
        async def communicate(self, input=None):
            captured['body'] = json.loads(input)
            return json.dumps({'protocol': 'nap-build-runner/1',
                'operation_id': request['operation_id'], 'generation': 1, 'job_id': None,
                'status': 'not_found', 'max_generation': 0, 'closed': False,
                'observed_at': '2026-10-25T00:00:00Z', 'result': {'free_bytes': 2048}}).encode(), b''
    async def start(*args, **kwargs):
        captured['argv'] = args
        assert kwargs.get('shell') is not True
        return Process()
    entry = builder_host.model_dump() if as_dict else builder_host
    result = await BuildRunnerClient(hosts={'lab': entry}, start_process=start).execute(request, host_id='lab')
    assert result['status'] == 'not_found'
    assert captured['body'] == request
    assert captured['argv'][-2:] == ('builder.invalid', 'nap-build-runner')
    assert 'StrictHostKeyChecking=yes' in captured['argv']
    assert '2222' in captured['argv']
    assert 'scope-lab' not in captured['argv']


async def test_builder_no_relaja_permisos_de_clave_ssh(builder_host):
    from pathlib import Path
    Path(builder_host.private_key_path).chmod(0o644)
    async def never(*args, **kwargs):
        raise AssertionError('No debe contactar un destino con clave insegura')
    with pytest.raises(RunnerError):
        await BuildRunnerClient(hosts={'lab': builder_host}, start_process=never).execute(status_request(), host_id='lab')
