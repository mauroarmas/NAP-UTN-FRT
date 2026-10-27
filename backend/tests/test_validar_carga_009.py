"""El generador nunca admite una base operativa ni expone credenciales."""
import json
import os

import pytest

from scripts.validar_carga import load_private, validate_url, fixture_sql, SAMPLES_PER_SERVICE


@pytest.mark.parametrize('url', [
    'sqlite+aiosqlite:///test.db',
    'postgresql+asyncpg://nap_perf:secret@172.16.36.100:55434/nap_perf_009',
    'postgresql+asyncpg://nap_perf:secret@localhost:5432/nap_perf_009',
    'postgresql+asyncpg://nap_lab:secret@localhost:55434/nap_perf_009',
    'postgresql+asyncpg://nap_perf:secret@localhost:55434/ps_db',
    'postgresql+asyncpg://nap_perf:secret@localhost:55434/nap_perf_009?host=other',
])
def test_rejects_other_databases_without_echoing_password(url):
    with pytest.raises(ValueError) as exc:
        validate_url(url)
    assert 'secret' not in str(exc.value) and '://' not in str(exc.value)


def test_only_explicit_loopback_fixture_database():
    validate_url('postgresql+asyncpg://nap_perf:secret@127.0.0.1:55434/nap_perf_009')


def test_config_rejects_world_readable_links_and_duplicate_keys(tmp_path):
    config = tmp_path / 'config.json'
    config.write_text('{"run_id":"a","run_id":"b"}')
    config.chmod(0o600)
    with pytest.raises(ValueError):
        load_private(config)
    config.write_text(json.dumps({'run_id': 'a'}))
    assert load_private(config)['run_id'] == 'a'
    config.chmod(0o644)
    with pytest.raises(ValueError):
        load_private(config)
    config.chmod(0o600)
    link = tmp_path / 'link'
    link.symlink_to(config)
    with pytest.raises((ValueError, OSError)):
        load_private(link)


def test_generates_exact_full_window_with_bound_parameters():
    assert SAMPLES_PER_SERVICE == 90 * 24 * 60 == 129600
    sql = fixture_sql()
    assert 'generate_series(0, :last_sample)' in sql
    assert ':service_id' in sql and ':cutoff' in sql
    assert 'intervalo_at' in sql and 'net_in_delta' in sql
    assert 'DROP' not in sql.upper()
