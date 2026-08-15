"""Fixtures compartidas: base en memoria, cliente HTTP y doble de Proxmox."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import (  # noqa: F401 — registra las tablas en Base.metadata
    Catedra,
    MetricaSnapshot,
    Pedido,
    PedidoHistorial,
    RecursoTemplate,
    Servicio,
    Usuario,
)
from app.models.usuario import RolUsuario
from app.utils.security import create_access_token

from tests import factories
from tests.fakes import FakeProxmoxClient


@pytest_asyncio.fixture
async def engine():
    """Engine SQLite en memoria compartido por todas las conexiones de la prueba."""
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db(engine) -> AsyncSession:
    """Sesión de base de datos por prueba."""
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        yield session


@pytest_asyncio.fixture
async def client(engine, db) -> AsyncClient:
    """Cliente HTTP contra la app, con la dependencia de base sustituida."""

    async def _get_db_override():
        yield db

    app.dependency_overrides[get_db] = _get_db_override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
def proxmox(monkeypatch) -> FakeProxmoxClient:
    """
    Sustituye el cliente Proxmox por el doble de prueba.

    Se pisa el singleton del módulo en lugar de la función: así queda cubierto
    todo sitio que llame a ``get_proxmox_client()``, sin importar cómo lo haya
    importado (a nivel de módulo o dentro de una función).
    """
    fake = FakeProxmoxClient()
    monkeypatch.setattr("app.services.proxmox_client._proxmox_client", fake)
    return fake


# --- Datos base y autenticación ---


@pytest_asyncio.fixture
async def catedra(db) -> Catedra:
    return await factories.crear_catedra(db)


@pytest_asyncio.fixture
async def admin(db) -> Usuario:
    return await factories.crear_usuario(db, "admin", rol=RolUsuario.ADMIN)


@pytest_asyncio.fixture
async def usuario_catedra(db, catedra) -> Usuario:
    return await factories.crear_usuario(
        db, "profe", rol=RolUsuario.CATEDRA_ADMIN, catedra_id=catedra.id
    )


@pytest_asyncio.fixture
async def template(db) -> RecursoTemplate:
    return await factories.crear_template(db)


def _headers(usuario: Usuario) -> dict:
    token = create_access_token({"sub": usuario.username, "rol": usuario.rol.value})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_admin(admin) -> dict:
    """Cabeceras con JWT válido de administrador."""
    return _headers(admin)


@pytest.fixture
def auth_catedra(usuario_catedra) -> dict:
    """Cabeceras con JWT válido de responsable de cátedra."""
    return _headers(usuario_catedra)
