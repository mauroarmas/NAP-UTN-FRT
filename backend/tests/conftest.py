"""Fixtures compartidas: base en memoria, cliente HTTP y doble de Proxmox."""

from types import SimpleNamespace
import os
from pathlib import Path

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
from tests.auth_helpers import headers_para

from tests import factories
from tests.fakes import FakeProxmoxClient
from tests.network import block_network
from app.services.email_service import despachar_email as REAL_EMAIL_SENDER


def pytest_addoption(parser):
    parser.addoption('--require-postgres', action='store_true', help='Exigir TEST_DATABASE_URL explícita')


def pytest_configure(config):
    config.addinivalue_line('markers', 'postgres: requiere PostgreSQL 16 de pruebas aislado')
    explicit_pg = any('tests/postgres' in str(arg).replace('\\', '/') for arg in config.args)
    if (config.getoption('--require-postgres') or explicit_pg) and not os.environ.get('TEST_DATABASE_URL'):
        raise pytest.UsageError('Configurar TEST_DATABASE_URL para las pruebas PostgreSQL (backend/README.md)')


def pytest_collection_modifyitems(config, items):
    for item in items:
        if Path(__file__).parent / 'postgres' in Path(item.path).parents:
            item.add_marker(pytest.mark.postgres)
            if not os.environ.get('TEST_DATABASE_URL'):
                item.add_marker(pytest.mark.skip(reason='Requiere TEST_DATABASE_URL; job PostgreSQL obligatorio en CI'))


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    block_network(monkeypatch, allow_postgres=True)


@pytest.fixture(autouse=True)
def isolated_auth_configuration(monkeypatch):
    from cryptography.fernet import Fernet
    from app.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, 'app_env', 'development')
    monkeypatch.setattr(settings, 'app_frontend_url', 'http://test')
    monkeypatch.setattr(settings, 'csrf_secret', 'test-only-independent-csrf-key-009')
    monkeypatch.setattr(settings, 'secret_keyring', {'test': Fernet.generate_key().decode()})
    monkeypatch.setattr(settings, 'secret_active_key', 'test')


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
    async with AsyncClient(transport=transport, base_url="http://test/api/v1", headers={'Origin': 'http://test', 'X-NAP-Request': '1'}) as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def proxmox(monkeypatch) -> FakeProxmoxClient:
    """
    Sustituye el cliente Proxmox por el doble de prueba.

    Se pisa el singleton del módulo en lugar de la función: así queda cubierto
    todo sitio que llame a ``get_proxmox_client()``, sin importar cómo lo haya
    importado (a nivel de módulo o dentro de una función).

    Es ``autouse`` a propósito: un test que no lo pedía salía a hablar con el
    clúster real en cuanto el código empezó a consultar el estado antes de cada
    acción, y llegó a pasar por casualidad porque el VMID de las factories
    coincidía con uno real. Ninguna prueba debe depender de la red.
    """
    fake = FakeProxmoxClient()
    monkeypatch.setattr("app.services.proxmox_client._proxmox_client", fake)
    monkeypatch.setattr("app.services.proxmox_client.get_proxmox_factory", lambda: lambda: fake)
    return fake


# --- Datos base y autenticación ---


@pytest_asyncio.fixture
async def admin(db) -> Usuario:
    return await factories.crear_usuario(db, "admin", rol=RolUsuario.ADMIN)


@pytest_asyncio.fixture
async def usuario_catedra(db) -> Usuario:
    """Responsable de cátedra. La cátedra se le cuelga en el fixture `catedra`."""
    return await factories.crear_usuario(db, "profe", rol=RolUsuario.CATEDRA_ADMIN)


@pytest_asyncio.fixture
async def catedra(db, usuario_catedra) -> Catedra:
    """Cátedra cuyo titular es `usuario_catedra`.

    El orden se invirtió respecto del modelo anterior: antes el usuario apuntaba
    a su cátedra, ahora la cátedra apunta a su titular, así que hay que crear a
    la persona primero.
    """
    return await factories.crear_catedra(db, titular_id=usuario_catedra.id)


@pytest_asyncio.fixture
async def usuario_multicatedra(db):
    """Persona con dos cátedras propias, más una tercera cátedra ajena poblada.

    Es el escenario base de las pruebas de aislamiento: sin una cátedra ajena
    con datos reales, un filtro roto pasa desapercibido porque no hay nada que
    se pueda filtrar de más.
    """
    titular = await factories.crear_usuario(db, "multi", rol=RolUsuario.CATEDRA_ADMIN)
    propias = [
        await factories.crear_catedra(db, nombre="Propia A", titular_id=titular.id),
        await factories.crear_catedra(db, nombre="Propia B", titular_id=titular.id),
    ]

    ajeno = await factories.crear_usuario(db, "ajeno", rol=RolUsuario.CATEDRA_ADMIN)
    ajena = await factories.crear_catedra(db, nombre="Ajena", titular_id=ajeno.id)

    template = await factories.crear_template(db, nombre="LXC para aislamiento")
    for cat in (*propias, ajena):
        solicitante = ajeno if cat is ajena else titular
        pedido = await factories.crear_pedido(
            db,
            catedra_id=cat.id,
            solicitante_id=solicitante.id,
            template_id=template.id,
        )
        await factories.crear_servicio(
            db,
            catedra_id=cat.id,
            template_id=template.id,
            pedido_id=pedido.id,
            proxmox_vmid=str(200 + cat.id),
        )

    return SimpleNamespace(
        titular=titular,
        propias=propias,
        ajeno=ajeno,
        ajena=ajena,
        template=template,
        headers=await headers_para(db, titular),
    )


@pytest_asyncio.fixture
async def template(db) -> RecursoTemplate:
    return await factories.crear_template(db)


@pytest_asyncio.fixture
async def auth_admin(admin, db) -> dict:
    """Cookie/CSRF de dominio; no prueba ingreso ni habilitación MFA."""
    return await headers_para(db, admin)


@pytest_asyncio.fixture
async def auth_catedra(usuario_catedra, db) -> dict:
    return await headers_para(db, usuario_catedra)


@pytest.fixture(autouse=True)
def mock_email(monkeypatch) -> list[dict]:
    """Captura los correos despachados para inspección en tests y evita envíos reales."""
    enviados = []

    def _fake_despachar(destinatarios, asunto, texto_plano, html_contenido, **kwargs):
        enviados.append({
            "destinatarios": destinatarios,
            "asunto": asunto,
            "texto_plano": texto_plano,
            "html_contenido": html_contenido,
        })

    monkeypatch.setattr("app.services.email_service.despachar_email", _fake_despachar)
    return enviados

