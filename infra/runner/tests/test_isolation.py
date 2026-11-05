import socket
import subprocess

import pytest


def test_runner_suite_cannot_open_ssh_or_http_by_accident():
    with socket.socket() as client, pytest.raises(RuntimeError, match='Red real prohibida'):
        client.connect(('192.0.2.1', 22))


def test_runner_suite_requires_fake_executor():
    with pytest.raises(RuntimeError, match='Proceso externo prohibido'):
        subprocess.run(['ssh', 'example.invalid', 'true'], check=True)
