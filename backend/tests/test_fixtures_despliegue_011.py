"""Verifica que los dobles exponen los fallos que deben detectar las suites 011."""

import httpx
import pytest

from tests.fixtures.despliegue_011 import FakeApplicationRunner
from app.utils.clock import clock as PREVIOUSLY_IMPORTED_CLOCK


def test_create_lost_response_preserves_stopped_guest(pve_011):
    pve_011.lose_create_response = True
    with pytest.raises(TimeoutError):
        pve_011.create_lxc('pve1', vmid=1234, rootfs='local-lvm:8', start=0)
    assert len(pve_011.creados) == 1
    assert pve_011.get_lxc_config('pve1', 1234)['start'] == 0
    assert pve_011.estados[1234] == 'stopped'


async def test_worker_restart_and_takeover_do_not_restart_job(runner_011, node_store_011):
    request = {'action': 'start', 'execution_id': 'fixture-execution', 'lease_generation': 1,
               'configuracion_sha256': 'a' * 64, 'secrets': {'password': 'do-not-store'}}
    runner_011.lose_start_response = True
    with pytest.raises(TimeoutError):
        await runner_011.execute(request)
    restarted = FakeApplicationRunner(node_store_011)
    result = await restarted.execute({**request, 'lease_generation': 2})
    assert result['estado'] == 'ejecutando'
    assert node_store_011.effects == ['fixture-execution']
    assert 'do-not-store' not in repr(node_store_011)
    with pytest.raises(ValueError, match='STALE_CONTROLLER'):
        await runner_011.execute(request)
    with pytest.raises(ValueError, match='EXECUTION_CONFLICT'):
        await restarted.execute({**request, 'lease_generation': 3, 'configuracion_sha256': 'b' * 64})


async def test_node_reboot_is_uncertain_not_new_execution(runner_011, node_store_011):
    request = {'action': 'start', 'execution_id': 'fixture-execution'}
    await runner_011.execute(request)
    node_store_011.boot_id = 'different-boot'
    result = await runner_011.execute({**request, 'action': 'status'})
    assert result['estado'] == 'incierto'
    assert len(node_store_011.effects) == 1


async def test_registry_supports_private_auth_and_frozen_digest(registry_011):
    old = registry_011.add_image(private=True)
    registry_011.add_image(volumes=['/data'], private=True)  # Mover el mismo tag.
    async with httpx.AsyncClient(transport=registry_011.transport()) as client:
        url = 'https://registry.test/v2/campus/demo/manifests/' + old['manifest_digest']
        assert (await client.get(url)).status_code == 401
        result = await client.get(url, headers={'Authorization': 'Bearer fixture-registry-read-token'})
        assert result.json() == old['manifest']
    assert 'fixture-registry-read-token' not in repr(registry_011.calls)


async def test_catedras_have_different_current_owners(catedras_011):
    assert len({c.id for c in catedras_011.catedras}) == 2
    assert {c.titular_id for c in catedras_011.catedras} == {u.id for u in catedras_011.titulares}


def test_clock_is_injectable(clock_011):
    from app.utils import clock as module
    before = module.clock.now()
    clock_011.advance(seconds=30)
    assert (module.clock.now() - before).total_seconds() == 30
    assert PREVIOUSLY_IMPORTED_CLOCK.now() == clock_011.now()
