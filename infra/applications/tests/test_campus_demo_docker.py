"""Ensayo Docker local opt-in; no demuestra Docker anidado en Proxmox."""

import json
import subprocess
import time
from urllib.request import Request, urlopen
from uuid import uuid4

import pytest


@pytest.mark.integration
def test_demo_restart_persistence_and_two_independent_instances():
    run_id = uuid4().hex[:12]
    containers, volumes = [], []

    def docker(*args):
        return subprocess.run(['docker', *args], check=True, text=True, timeout=30,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.strip()

    def base_url(name):
        return 'http://' + docker('port', name, '8080/tcp')

    def create(suffix):
        name = f'nap011-fixture-{run_id}-{suffix}'
        volume = name + '-data'
        docker('volume', 'create', '--label', 'nap.fixture_run=' + run_id, volume)
        volumes.append(volume)
        docker('run', '-d', '--name', name, '--label', 'nap.fixture_run=' + run_id,
               '--mount', f'type=volume,source={volume},target=/data',
               '--publish', '127.0.0.1::8080', 'nap011-campus-demo:acceptance')
        containers.append(name)
        return name

    def request(base, path='/health', value=None):
        data = None if value is None else json.dumps(value).encode()
        req = Request(base + path, data=data, headers={'Content-Type': 'application/json'})
        with urlopen(req, timeout=2) as response:
            return json.load(response)

    def ready(name):
        # Docker puede asignar otro puerto efímero al reiniciar el contenedor.
        base = base_url(name)
        for _ in range(30):
            try:
                assert request(base) == {'status': 'ok'}
                return base
            except OSError:
                time.sleep(.2)
        pytest.fail('La aplicación de ensayo no arrancó')

    try:
        first = create('a')
        base = ready(first)
        assert request(base, '/api/note', {'note': 'Persistencia 011'}) == {'saved': True}
        docker('restart', first)
        base = ready(first)
        assert request(base, '/api/note')['note'] == 'Persistencia 011'
        second = create('b')
        assert request(ready(second), '/api/note')['note'] == ''
        assert json.loads(docker('inspect', '--format', '{{json .Config.User}}', first)) == '10001:10001'
    finally:
        for name in containers:
            labels = json.loads(docker('inspect', '--format', '{{json .Config.Labels}}', name))
            if labels.get('nap.fixture_run') == run_id:
                docker('rm', '-f', name)
        for name in volumes:
            labels = json.loads(docker('volume', 'inspect', '--format', '{{json .Labels}}', name))
            if labels.get('nap.fixture_run') == run_id:
                docker('volume', 'rm', name)
