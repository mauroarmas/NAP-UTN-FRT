"""La espera de arranque de la comprobación es acotada, configurable por nodo y falla cerrada."""
import json
import os

import pytest

from infra.applications.docker import probes
from infra.applications.job.protocol import JobError


def write(path, value, mode=0o600):
    path.write_text(value if isinstance(value, str) else json.dumps(value))
    os.chmod(path, mode)
    return path


def test_defaults_are_longer_than_the_historic_database_window(tmp_path):
    missing = tmp_path/'limits.json'
    assert probes.ready_wait('database', path=missing) == 300 > 120
    assert probes.ready_wait('web', path=missing) == 90


def test_node_file_overrides_each_kind_independently(tmp_path):
    path = write(tmp_path/'limits.json', {'schema_version': 'nap-application-limits/1', 'espera_base_datos_segundos': 450})
    assert probes.ready_wait('database', path=path) == 450
    assert probes.ready_wait('web', path=path) == 90


@pytest.mark.parametrize('content', [
    {'schema_version': 'nap-application-limits/1', 'espera_base_datos_segundos': 59},
    {'schema_version': 'nap-application-limits/1', 'espera_base_datos_segundos': 601},
    {'schema_version': 'nap-application-limits/1', 'espera_web_segundos': 29},
    {'schema_version': 'nap-application-limits/1', 'espera_base_datos_segundos': True},
    {'schema_version': 'nap-application-limits/1', 'espera_base_datos_segundos': 120.5},
    {'schema_version': 'nap-application-limits/1', 'otra_clave': 1},
    {'schema_version': 'otra/1', 'espera_base_datos_segundos': 200},
    '{"schema_version":"nap-application-limits/1","schema_version":"x"}',
    'no es json',
])
def test_invalid_node_file_fails_closed_instead_of_using_defaults(tmp_path, content):
    with pytest.raises(JobError) as error:
        probes.ready_wait('database', path=write(tmp_path/'limits.json', content))
    assert error.value.code == 'PROFILE_UNAVAILABLE'


def test_group_writable_file_and_symlink_are_rejected(tmp_path):
    path = write(tmp_path/'limits.json', {'schema_version': 'nap-application-limits/1'}, mode=0o620)
    with pytest.raises(JobError):
        probes.ready_wait('database', path=path)
    real = write(tmp_path/'real.json', {'schema_version': 'nap-application-limits/1'})
    link = tmp_path/'link.json'
    link.symlink_to(real)
    with pytest.raises(JobError):
        probes.ready_wait('database', path=link)
