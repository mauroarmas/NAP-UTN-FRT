import asyncio
import threading
import time

import pytest


async def test_four_threads_bound_real_io_even_after_callers_timeout():
    from app.services.infraestructura_io import ejecutar, InfraNoVerificable
    lock = threading.Lock()
    active = maximum = 0
    def slow():
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
        time.sleep(0.08)
        with lock:
            active -= 1
        return 'observado'
    results = await asyncio.gather(*(ejecutar(slow, timeout=0.01) for _ in range(12)), return_exceptions=True)
    assert all(isinstance(result, InfraNoVerificable) for result in results)
    # Terminan los cuatro que ya habían comenzado; los encolados se cancelan.
    await asyncio.sleep(0.12)
    assert maximum <= 4 and active == 0


async def test_sync_work_does_not_block_event_loop():
    from app.services.infraestructura_io import ejecutar
    signal = asyncio.Event()
    task = asyncio.create_task(ejecutar(lambda: time.sleep(0.05), timeout=1))
    async def independent():
        await asyncio.sleep(0)
        signal.set()
    await independent()
    assert signal.is_set() and not task.done()
    await task


async def test_query_404_is_explicit_absence_and_post_timeout_is_uncertain(monkeypatch):
    from app.services.infraestructura_io import consultar, enviar, InfraNoVerificable
    class Missing(Exception):
        status_code = 404
    class Client:
        def get_lxc_config(self, node, vmid):
            raise Missing()
        def start_lxc(self, node, vmid):
            raise TimeoutError('Untrusted response containing credentials')
    observation = await consultar('get_lxc_config', 'pve1', 100, pve=Client())
    assert observation.estado == 'ausente' and observation.valor is None
    with pytest.raises(InfraNoVerificable) as failed:
        await enviar('start_lxc', 'pve1', 100, pve=Client())
    assert failed.value.incierto and 'credentials' not in str(failed.value)


async def test_server_failure_never_proves_absence():
    from app.services.infraestructura_io import consultar, InfraNoVerificable
    class Failed(Exception):
        status_code = 500
    class Client:
        def get_lxc_config(self, *args):
            raise Failed('Resource not found, but absence is not established')
    with pytest.raises(InfraNoVerificable):
        await consultar('get_lxc_config', 'pve1', 100, pve=Client())


async def test_parallel_calls_use_and_close_independent_clients(monkeypatch):
    from app.services.infraestructura_io import consultar
    clients = []
    class Client:
        def __init__(self):
            self.closed = False
            clients.append(self)
        def get_nodes(self):
            time.sleep(0.01)
            return []
        def close(self):
            self.closed = True
    monkeypatch.setattr('app.services.proxmox_client.get_proxmox_factory', lambda: Client)
    await asyncio.gather(*(consultar('get_nodes') for _ in range(4)))
    assert len(clients) == 4 and all(client.closed for client in clients)
