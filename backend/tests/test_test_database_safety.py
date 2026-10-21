import pytest

from tests.postgres.safety import validate_test_database_url

TEST_URL = 'postgresql+asyncpg://nap_test:test@127.0.0.1:55432/nap_test_009'


@pytest.mark.parametrize('url', [
    'postgresql+asyncpg://ps_user:test@127.0.0.1/ps_db',
    'postgresql+asyncpg://nap_test:test@cluster.example/nap_test_009',
    'postgresql+asyncpg://nap_test:test@127.0.0.1/nap_test_009?options=unsafe',
    'sqlite+aiosqlite:///nap_test_009',
    'not a URL',
])
def test_reject_unsafe_database_before_connecting(url):
    with pytest.raises(ValueError):
        validate_test_database_url(url)


def test_reject_operational_database_even_with_test_name():
    with pytest.raises(ValueError, match='operativa'):
        validate_test_database_url(TEST_URL, TEST_URL)


def test_accept_local_dedicated_database():
    assert validate_test_database_url(TEST_URL) == TEST_URL


def test_loopback_alias_and_default_port_cannot_bypass_operational_guard():
    with pytest.raises(ValueError, match='operativa'):
        validate_test_database_url(
            'postgresql+asyncpg://nap_test:test@127.0.0.1:5432/nap_test_009',
            'postgresql://nap_test:other@localhost/nap_test_009',
        )
