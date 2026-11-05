"""La exclusión y el rollback de idempotencia requieren PostgreSQL real."""

import asyncio

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.catedra import Catedra


async def test_same_key_concurrent_produces_one_effect(pg_sessions, admin):
    from app.services.idempotencia_service import ejecutar, ResultadoDecision
    barrier = asyncio.Barrier(2)

    async def request():
        async with pg_sessions() as session, session.begin():
            await barrier.wait()

            async def decide(db):
                entity = Catedra(nombre='Decisión única')
                db.add(entity)
                await db.flush()
                return ResultadoDecision(201, {'id': entity.id})

            return await ejecutar(session, actor_id=admin.id, clave='same-key', metodo='POST',
                                  ruta='/catedras/', payload={'nombre': 'Decisión única'}, decidir=decide)

    first, second = await asyncio.gather(request(), request())
    assert first.resultado == second.resultado
    assert {first.replayed, second.replayed} == {False, True}
    async with pg_sessions() as db:
        rows = (await db.execute(select(Catedra).where(Catedra.nombre == 'Decisión única'))).scalars().all()
        assert len(rows) == 1


async def test_key_reuse_with_different_payload_conflicts(pg_sessions, admin):
    from app.services.idempotencia_service import ejecutar, ResultadoDecision

    async def decide(db):
        return ResultadoDecision(200, {'confirmado': True})

    args = dict(actor_id=admin.id, clave='payload-key', metodo='POST', ruta='/prueba', decidir=decide)
    async with pg_sessions() as db, db.begin():
        await ejecutar(db, payload={'valor': 1}, **args)
    async with pg_sessions() as db, db.begin():
        with pytest.raises(HTTPException) as exc:
            await ejecutar(db, payload={'valor': 2}, **args)
        assert exc.value.status_code == 409


async def test_rollback_does_not_leave_a_confirmed_key_or_partial_effect(pg_sessions, admin):
    from app.services.idempotencia_service import ejecutar, ResultadoDecision

    async def fail(db):
        db.add(Catedra(nombre='Rollback completo'))
        await db.flush()
        raise RuntimeError('fallo antes del commit')

    args = dict(actor_id=admin.id, clave='rollback-key', metodo='POST', ruta='/prueba', payload={})
    with pytest.raises(RuntimeError):
        async with pg_sessions() as db, db.begin():
            await ejecutar(db, decidir=fail, **args)

    async def succeed(db):
        row = Catedra(nombre='Rollback completo')
        db.add(row)
        await db.flush()
        return ResultadoDecision(201, {'id': row.id})

    async with pg_sessions() as db, db.begin():
        result = await ejecutar(db, decidir=succeed, **args)
        assert not result.replayed
