import asyncio
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select

from app.models.operacion_infraestructura import OperacionInfraestructura
from app.utils.clock import clock


async def pending(db, *, key='lease-test', phase='preparacion'):
    value = OperacionInfraestructura(tipo='desplegar', actor_tipo='sistema', actor_id_normalizado='test-worker',
        idempotency_key=key, request_hash='a' * 64, estado='pendiente', fase=phase, next_poll_at=clock.now())
    db.add(value)
    await db.commit()
    return value


async def test_skip_locked_claims_each_operation_once(db, pg_sessions):
    from app.services.operacion_service import reclamar
    entries = [await pending(db, key=f'lease-{index}') for index in range(4)]
    barrier = asyncio.Barrier(4)
    async def claim():
        async with pg_sessions() as session, session.begin():
            await barrier.wait()
            return await reclamar(session, owner=uuid4())
    claims = await asyncio.gather(*(claim() for _ in range(4)))
    assert {item.id for item in claims} == {item.id for item in entries}
    assert len({item.id for item in claims}) == 4


async def test_expired_lease_cannot_confirm_or_release_new_owner(db, pg_sessions, monkeypatch):
    from app.services.operacion_service import reclamar, heartbeat, terminar
    now = clock.now()
    monkeypatch.setattr(clock, 'now', lambda: now)
    entry = await pending(db)
    first = await reclamar(db, owner=uuid4(), lease_seconds=30)
    await db.commit()
    now += timedelta(seconds=31)
    async with pg_sessions() as session, session.begin():
        second = await reclamar(session, owner=uuid4(), lease_seconds=30)
    assert second.id == first.id and second.generation > first.generation
    assert not await heartbeat(db, first)
    assert not await terminar(db, first, estado='confirmada')
    await db.commit()
    await db.refresh(entry)
    assert entry.lease_owner == second.owner and entry.estado == 'en_curso'


async def test_takeover_preserves_dispatch_marker_instead_of_resetting_for_retry(db, monkeypatch):
    from app.services.operacion_service import reclamar
    now = clock.now()
    monkeypatch.setattr(clock, 'now', lambda: now)
    entry = await pending(db, phase='dispatch_started')
    first = await reclamar(db, owner=uuid4(), lease_seconds=30)
    await db.commit()
    now += timedelta(seconds=31)
    second = await reclamar(db, owner=uuid4(), lease_seconds=30)
    await db.commit()
    await db.refresh(entry)
    assert entry.fase == 'dispatch_started' and entry.upid is None
    assert second.generation > first.generation


async def test_stale_job_owner_cannot_delete_successor(db, pg_sessions, monkeypatch):
    from app.services.scheduler import adquirir_job, liberar_job
    from app.models.job_lock import JobLock
    now = clock.now()
    monkeypatch.setattr(clock, 'now', lambda: now)
    first = await adquirir_job(db, 'test-job')
    now += timedelta(seconds=31)
    async with pg_sessions() as session:
        second = await adquirir_job(session, 'test-job')
    assert not await liberar_job(db, first)
    current = await db.get(JobLock, 'test-job', populate_existing=True)
    assert current.owner_token == second.owner and current.generation == second.generation


async def test_job_heartbeat_prevents_takeover(db, pg_sessions, monkeypatch):
    import pytest
    from app.services.scheduler import adquirir_job, renovar_job, LockNoDisponible
    now = clock.now()
    monkeypatch.setattr(clock, 'now', lambda: now)
    first = await adquirir_job(db, 'test-heartbeat')
    now += timedelta(seconds=25)
    assert await renovar_job(db, first)
    now += timedelta(seconds=6)
    async with pg_sessions() as session:
        with pytest.raises(LockNoDisponible):
            await adquirir_job(session, 'test-heartbeat')
