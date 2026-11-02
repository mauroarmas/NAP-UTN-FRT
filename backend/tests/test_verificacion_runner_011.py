"""Un runner que no se puede comprobar no autoriza aprobar ni desplegar; sin transporte no hay consulta."""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services.application_profiles_service import verify_node_profile

REFERENCE = {'id': 'docker-ubuntu24', 'revision': 4, 'sha256': 'a' * 64}


def entry(tmp_path, *, hosts_mode=0o644):
    key = tmp_path/'key'; key.write_text('fake-key-not-used'); key.chmod(0o600)
    hosts = tmp_path/'known_hosts'; hosts.write_text('pve-test.invalid ssh-ed25519 TEST-ONLY'); hosts.chmod(hosts_mode)
    return {'host': 'pve-test.invalid', 'user': 'naprunner', 'port': 22,
            'private_key_path': str(key), 'known_hosts_path': str(hosts)}


@pytest.fixture(autouse=True)
def no_ssh_process(monkeypatch):
    async def forbidden(*args, **kwargs):
        pytest.fail('No se envían trabajos ni se abre SSH al comprobar un transporte inválido')
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', forbidden)


async def test_without_any_configured_transport_the_check_is_skipped():
    assert await verify_node_profile(REFERENCE, node='pve1', settings=SimpleNamespace(runner_nodes={})) is None


async def test_configured_runners_but_missing_node_entry_rejects(tmp_path):
    settings = SimpleNamespace(runner_nodes={'pve2': entry(tmp_path)})
    with pytest.raises(HTTPException) as error:
        await verify_node_profile(REFERENCE, node='pve1', settings=settings)
    assert error.value.status_code == 409 and error.value.detail['codigo'] == 'perfil_aplicacion_no_disponible'


@pytest.mark.parametrize('mode', [0o664, 0o666, 0o620])
async def test_known_hosts_with_group_or_world_write_permissions_rejects_without_ssh(tmp_path, mode):
    settings = SimpleNamespace(runner_nodes={'pve1': entry(tmp_path, hosts_mode=mode)})
    with pytest.raises(HTTPException) as error:
        await verify_node_profile(REFERENCE, node='pve1', settings=settings)
    assert error.value.status_code == 409 and error.value.detail['codigo'] == 'perfil_aplicacion_no_disponible'


async def test_malformed_runner_entry_rejects(tmp_path):
    broken = entry(tmp_path); broken.pop('port')
    with pytest.raises(HTTPException) as error:
        await verify_node_profile(REFERENCE, node='pve1', settings=SimpleNamespace(runner_nodes={'pve1': broken}))
    assert error.value.status_code == 409
