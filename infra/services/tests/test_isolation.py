import socket
import subprocess

import pytest


def test_builder_suite_cannot_download_or_execute_real_builds():
    with pytest.raises(RuntimeError, match='DNS real prohibido'):
        socket.getaddrinfo('example.invalid', 443)
    with pytest.raises(RuntimeError, match='Proceso externo prohibido'):
        subprocess.run(['docker', 'build', '.'], check=True)
