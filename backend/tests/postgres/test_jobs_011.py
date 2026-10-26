"""Carreras reales de intentos/secretos; no acredita creación de invitados."""
import asyncio
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError

from app.models.identidad_infraestructura import IdentidadInfraestructura
from app.models.intento_despliegue import IntentoDespliegue
from app.models.operacion_infraestructura import OperacionInfraestructura
from app.models.secreto_despliegue import SecretoDespliegue
from app.models.reserva_red_aplicacion import ReservaRedAplicacion
from app.services.operacion_service import reclamar
from app.services.secreto_despliegue_service import asegurar
from app.utils.clock import clock
from tests.test_secretos_despliegue_011 import pedido_app  # shared fixture


async def seed_operation(db):
    identity = IdentidadInfraestructura(cluster_id=str(uuid4()), nodo='pve1', vmid=500,
        pool_catedra='fixture', nonce_cifrado='fixture-ciphertext', estado='reclamada')
    db.add(identity); await db.flush()
    operation = OperacionInfraestructura(tipo='desplegar', identidad_infraestructura_id=identity.id,
        actor_tipo='sistema', actor_id_normalizado='fixture', idempotency_key=str(uuid4()), request_hash='a'*64)
    db.add(operation); await db.flush()
    return identity, operation


async def test_concurrent_secret_creation_serializes_on_the_original_order(pg_sessions, db, admin, pedido_app):
    barrier = asyncio.Barrier(2)
    async def create():
        async with pg_sessions() as session, session.begin():
            await barrier.wait()
            return await asegurar(session, pedido_app.id, usuario=admin)
    first, second = await asyncio.wait_for(asyncio.gather(create(), create()), timeout=15)
    assert first == second
    assert await db.scalar(select(func.count()).select_from(SecretoDespliegue)) == 1


async def test_takeover_keeps_actual_attempt_number_and_execution_identity(db, pg_sessions, monkeypatch):
    identity, operation = await seed_operation(db)
    attempt = IntentoDespliegue(operacion_id=operation.id, operacion_raiz_id=operation.id,
        numero=1, identidad_infraestructura_id=identity.id, configuracion_sha256='b'*64)
    db.add(attempt); await db.commit()
    first_execution = attempt.execution_id
    now = clock.now(); monkeypatch.setattr(clock, 'now', lambda: now)
    first = await reclamar(db, owner=uuid4()); await db.commit()
    now += timedelta(seconds=31)
    async with pg_sessions() as session, session.begin(): second = await reclamar(session, owner=uuid4())
    await db.refresh(attempt); await db.refresh(operation)
    assert first.id == second.id and second.generation > first.generation
    assert operation.intento == 2 and attempt.numero == 1 and attempt.execution_id == first_execution
    assert await db.scalar(select(func.count()).select_from(IntentoDespliegue)) == 1


async def test_database_serializes_duplicate_effective_attempts(db, pg_sessions):
    identity, operation = await seed_operation(db); await db.commit()
    barrier = asyncio.Barrier(2)
    async def create():
        try:
            async with pg_sessions() as session, session.begin():
                await barrier.wait()
                session.add(IntentoDespliegue(operacion_id=operation.id, operacion_raiz_id=operation.id,
                    numero=1, identidad_infraestructura_id=identity.id, configuracion_sha256='b'*64))
                await session.flush()
            return True
        except IntegrityError: return False
    assert sorted(await asyncio.wait_for(asyncio.gather(create(), create()), timeout=15)) == [False, True]
    assert await db.scalar(select(func.count()).select_from(IntentoDespliegue)) == 1


async def test_active_address_cannot_be_shared_and_release_preserves_history(db, pg_sessions):
    first_identity, _ = await seed_operation(db)
    second_identity = IdentidadInfraestructura(cluster_id=first_identity.cluster_id, nodo='pve1', vmid=501,
        pool_catedra='fixture', nonce_cifrado='fixture-second', estado='reclamada')
    db.add(second_identity); await db.commit()
    barrier = asyncio.Barrier(2)
    async def reserve(identity_id, slot_id):
        try:
            async with pg_sessions() as session, session.begin():
                await barrier.wait()
                row = ReservaRedAplicacion(identidad_id=identity_id, cluster_id=first_identity.cluster_id,
                    perfil_id='fixture-network', perfil_revision=1, slot_id=slot_id, address='10.80.0.10',
                    mac='02:00:00:00:00:01', host='fixture.example.edu', snapshot={})
                session.add(row); await session.flush()
            return True
        except IntegrityError: return False
    assert sorted(await asyncio.wait_for(asyncio.gather(reserve(first_identity.id, 'slot-1'),
        reserve(second_identity.id, 'slot-2')), timeout=15)) == [False, True]
    row = await db.scalar(select(ReservaRedAplicacion))
    row.liberada_at = clock.now(); await db.commit()
    assert await db.scalar(select(func.count()).select_from(ReservaRedAplicacion)) == 1
