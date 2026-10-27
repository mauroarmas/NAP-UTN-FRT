"""Esquema aleatorio por prueba y sesiones PostgreSQL independientes."""

import os
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.database import Base
from tests.postgres.safety import validate_test_database_url


@pytest_asyncio.fixture
async def engine():
    value = os.environ.get('TEST_DATABASE_URL')
    if not value:
        pytest.fail('Las pruebas PostgreSQL requieren TEST_DATABASE_URL explícita; consultar backend/README.md')
    try:
        validate_test_database_url(value, get_settings().database_url)
    except ValueError as exc:
        pytest.fail(str(exc))
    schema = 'nap_test_' + uuid4().hex
    control = create_async_engine(value, connect_args={'timeout': 5})
    test_engine = None
    created = False
    try:
        async with control.begin() as conn:
            version = int(await conn.scalar(text('SHOW server_version_num')))
            if not 160000 <= version < 170000:
                pytest.fail('Esta suite requiere PostgreSQL 16')
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            created = True
        test_engine = create_async_engine(value, connect_args={
            'timeout': 5,
            'server_settings': {'search_path': schema, 'application_name': 'nap009-tests'},
        })
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        yield test_engine
    finally:
        if test_engine is not None:
            await test_engine.dispose()
        if created:
            # Solo el esquema generado en esta fixture, nunca DROP DATABASE ni public.
            async with control.begin() as conn:
                await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await control.dispose()


@pytest.fixture
def pg_sessions(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def empty_pg_schema():
    """Mismo aislamiento, sin create_all: Alembic debe construir el esquema."""
    value = os.environ.get('TEST_DATABASE_URL')
    if not value:
        pytest.fail('TEST_DATABASE_URL requerida')
    validate_test_database_url(value, get_settings().database_url)
    schema = 'nap_test_' + uuid4().hex
    control = create_async_engine(value)
    isolated = None
    created = False
    try:
        async with control.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            created = True
        isolated = create_async_engine(value, connect_args={'server_settings': {'search_path': schema}})
        yield isolated
    finally:
        if isolated is not None:
            await isolated.dispose()
        if created:
            async with control.begin() as conn:
                await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await control.dispose()
