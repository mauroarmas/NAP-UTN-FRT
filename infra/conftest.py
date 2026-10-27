"""Los tests infra son puros por defecto: sin red ni procesos externos."""

import os
import subprocess

import pytest

from tests.network import block_network


def pytest_collection_modifyitems(config, items):
    for item in items:
        if 'integration' in item.keywords and os.environ.get('NAP_INFRA_INTEGRATION') != '1':
            item.add_marker(pytest.mark.skip(reason='Integración real deshabilitada'))


@pytest.fixture(autouse=True)
def isolated_infra(monkeypatch, request):
    if 'integration' in request.node.keywords and os.environ.get('NAP_INFRA_INTEGRATION') == '1':
        return
    block_network(monkeypatch)

    def blocked(*args, **kwargs):
        raise RuntimeError('Proceso externo prohibido: usar un doble del ejecutor')

    monkeypatch.setattr(subprocess, 'Popen', blocked)
