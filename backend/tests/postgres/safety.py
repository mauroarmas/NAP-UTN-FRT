"""Validación previa a cualquier conexión o limpieza de pruebas PostgreSQL."""

import re

from sqlalchemy.engine import make_url


def validate_test_database_url(value: str, operational_url: str | None = None) -> str:
    """Rechazar destinos ambiguos, externos u operativos sin exponer su URL."""
    try:
        url = make_url(value)
        operational = make_url(operational_url) if operational_url else None
    except Exception:
        raise ValueError('TEST_DATABASE_URL inválida') from None
    if (
        url.drivername != 'postgresql+asyncpg'
        or url.host not in {'localhost', '127.0.0.1', '::1', 'postgres_test'}
        or url.username != 'nap_test'
        or not re.fullmatch(r'nap_test_[a-z0-9_]+', url.database or '')
        or url.query
    ):
        raise ValueError('La base debe ser PostgreSQL de prueba local: usuario nap_test y base nap_test_*')
    def canonical_host(host):
        return 'loopback' if host in {'localhost', '127.0.0.1', '::1'} else host

    if operational and (canonical_host(url.host), url.port or 5432, url.database) == (
        canonical_host(operational.host), operational.port or 5432, operational.database
    ):
        raise ValueError('La base de prueba coincide con la base operativa')
    return value
