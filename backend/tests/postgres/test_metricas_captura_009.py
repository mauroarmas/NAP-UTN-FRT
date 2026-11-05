import asyncio
import threading

from sqlalchemy import func, select

from app.models.metrica import MetricaSnapshot
from app.models.servicio import Servicio
from app.services.metricas_service import capturar_snapshot_servicio
from tests.capacity_helpers import materializado, perfil_capacidad  # noqa: F401


async def test_two_captures_claim_one_minute_before_io_without_sharing_session(
    db, pg_sessions, proxmox, monkeypatch, perfil_capacidad, catedra, usuario_catedra, template,
):
    from app.utils.clock import clock
    now = clock.now().replace(second=10, microsecond=0)
    monkeypatch.setattr(clock, 'now', lambda: now)
    service, _ = await materializado(db, proxmox, catedra, usuario_catedra, template)
    entered, release, calls = threading.Event(), threading.Event(), []
    def read(node, vmid):
        calls.append(vmid)
        entered.set()
        if not release.wait(3):
            raise TimeoutError('doble sin liberación')
        return {'status': 'running', 'cpu': 0.1, 'mem': 128, 'disk': 1024,
            'netin': 2**54 + 1, 'netout': 2**54 + 3, 'uptime': 1000}
    monkeypatch.setattr(proxmox, 'get_lxc_status', read)
    async def capture():
        async with pg_sessions() as session:
            return await capturar_snapshot_servicio(session, await session.get(Servicio, service.id))
    first = asyncio.create_task(capture())
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        second = await asyncio.wait_for(capture(), timeout=2)
    finally:
        release.set()
        completed = await first
    assert second.id == completed.id
    assert completed.calidad == 'confirmada' and completed.net_in_bytes == 2**54 + 1
    assert len(calls) == 1
    assert await db.scalar(select(func.count()).select_from(MetricaSnapshot)) == 1
