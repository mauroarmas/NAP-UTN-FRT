"""Dobles de 011: efectos durables, registry OCI y fallos de transporte reproducibles.

La persistencia del nodo se comparte entre clientes simulados; reiniciar el cliente
no debe borrar el trabajo. Estos dobles no certifican perfiles de infraestructura.
"""

from copy import deepcopy
from dataclasses import dataclass, field
from hashlib import sha256
import json
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio

from tests import factories
from tests.fakes import FakeClock, FakeProxmoxClient


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


class ApplicationFakePVE(FakeProxmoxClient):
    """Respeta start=0 y permite perder la respuesta después del efecto real."""

    lose_create_response = False

    def create_lxc(self, node, **kwargs):
        result = super().create_lxc(node, **kwargs)
        vmid = int(kwargs.get('vmid', self.next_vmid))
        if kwargs.get('start') in (0, False):
            self.estados[vmid] = 'stopped'
            next(r for r in self.recursos if int(r.get('vmid', -1)) == vmid)['status'] = 'stopped'
        if self.lose_create_response:
            self.lose_create_response = False
            raise TimeoutError('Respuesta de create perdida después del efecto simulado')
        return result


class FakeOCIRegistry:
    """HTTPX MockTransport: digests reales de fixtures, tags mutables y auth local."""

    def __init__(self):
        self.documents = {}
        self.private = set()
        self.calls = []
        self.fail_paths = set()

    def add_image(self, repository='campus/demo', *, tag='acceptance', private=False, volumes=None):
        config = {'architecture': 'amd64', 'os': 'linux', 'config': {
            'Entrypoint': ['/app/server'], 'ExposedPorts': {'8080/tcp': {}},
            'Volumes': {p: {} for p in (volumes or [])},
        }}
        raw_config = canonical(config)
        config_digest = 'sha256:' + sha256(raw_config).hexdigest()
        manifest = {'schemaVersion': 2, 'mediaType': 'application/vnd.oci.image.manifest.v1+json',
                    'config': {'mediaType': 'application/vnd.oci.image.config.v1+json',
                               'digest': config_digest, 'size': len(raw_config)}, 'layers': []}
        raw = canonical(manifest)
        digest = 'sha256:' + sha256(raw).hexdigest()
        self.documents[f'/v2/{repository}/blobs/{config_digest}'] = raw_config
        for ref in (tag, digest):
            self.documents[f'/v2/{repository}/manifests/{ref}'] = raw
        if private:
            self.private.add(repository)
        return {'image': f'registry.test/{repository}:{tag}', 'manifest_digest': digest,
                'config_digest': config_digest, 'manifest': manifest, 'config': config}

    def handle(self, request):
        path = request.url.path
        self.calls.append((request.method, path))  # No almacenar Authorization.
        if path in self.fail_paths:
            raise httpx.ConnectError('Registry simulado inaccesible', request=request)
        if request.url.host != 'registry.test':
            raise AssertionError('Destino ajeno al registry de prueba')
        if path == '/token':
            return httpx.Response(200, json={'token': 'fixture-registry-read-token'})
        if any(path.startswith(f'/v2/{repo}/') for repo in self.private):
            if request.headers.get('authorization') != 'Bearer fixture-registry-read-token':
                return httpx.Response(401, headers={'WWW-Authenticate':
                    'Bearer realm="https://registry.test/token",service="registry.test"'})
        raw = self.documents.get(path)
        if raw is None:
            return httpx.Response(404, json={'errors': [{'code': 'MANIFEST_UNKNOWN'}]})
        return httpx.Response(200, content=raw, headers={
            'Content-Type': 'application/vnd.oci.image.manifest.v1+json' if '/manifests/' in path
                            else 'application/vnd.oci.image.config.v1+json',
            'Docker-Content-Digest': 'sha256:' + sha256(raw).hexdigest(),
        })

    def transport(self):
        return httpx.MockTransport(self.handle)


@dataclass
class DurableNodeStore:
    boot_id: str = field(default_factory=lambda: str(uuid4()))
    jobs: dict = field(default_factory=dict)
    effects: list = field(default_factory=list)


class FakeApplicationRunner:
    def __init__(self, store=None):
        self.store = store if store is not None else DurableNodeStore()
        self.lose_start_response = False

    async def execute(self, request):
        action = request['action']
        execution_id = request['execution_id']
        generation = request.get('lease_generation', 1)
        job = self.store.jobs.get(execution_id)
        if action == 'start':
            # Fingerprint del documento público: jamás persistir valores efectivos.
            public = {k: v for k, v in request.items() if k not in {
                'action', 'lease_generation', 'secretos', 'credentials', 'secrets'}}
            fingerprint = sha256(canonical(public)).hexdigest()
            if job and job['fingerprint'] != fingerprint:
                raise ValueError('EXECUTION_CONFLICT')
            if job is None:
                job = {'execution_id': execution_id, 'fingerprint': fingerprint,
                       'generation': generation, 'boot_id': self.store.boot_id,
                       'estado': 'ejecutando', 'items': [], 'ack': 0}
                self.store.jobs[execution_id] = job
                self.store.effects.append(execution_id)
        if job is None:
            raise ValueError('UNCONFIRMED')
        if generation < job['generation']:
            raise ValueError('STALE_CONTROLLER')
        job['generation'] = generation
        if action == 'start' and self.lose_start_response:
            self.lose_start_response = False
            raise TimeoutError('Respuesta de start perdida después del efecto simulado')
        if action == 'ack':
            cursor = request['through_seq']
            if not 0 <= cursor <= max((i['source_seq'] for i in job['items']), default=job['ack']):
                raise ValueError('INVALID_REQUEST')
            job['ack'] = max(job['ack'], cursor)
        elif action not in {'start', 'status', 'read'}:
            raise ValueError('INVALID_REQUEST')
        result = deepcopy(job)
        result['estado'] = job['estado'] if job['boot_id'] == self.store.boot_id else 'incierto'
        result['items'] = [i for i in result['items']
                           if i['source_seq'] > max(request.get('after', 0), job['ack'])]
        return result


@pytest.fixture
def clock_011(monkeypatch):
    clock = FakeClock()
    # También alcanza los módulos que importaron el singleton antes del fixture.
    monkeypatch.setattr('app.utils.clock.clock.now', clock.now)
    return clock


@pytest.fixture
def pve_011(monkeypatch):
    fake = ApplicationFakePVE()
    monkeypatch.setattr('app.services.proxmox_client._proxmox_client', fake)
    monkeypatch.setattr('app.services.proxmox_client.get_proxmox_factory', lambda: lambda: fake)
    return fake


@pytest.fixture
def registry_011():
    return FakeOCIRegistry()


@pytest.fixture
def node_store_011():
    return DurableNodeStore()


@pytest.fixture
def runner_011(node_store_011):
    return FakeApplicationRunner(node_store_011)


@pytest_asyncio.fixture
async def catedras_011(db):
    titulares = [await factories.crear_usuario(db, f'docente011_{n}') for n in (1, 2)]
    catedras = [await factories.crear_catedra(db, nombre=f'Cátedra 011 {n}', titular_id=u.id)
                for n, u in enumerate(titulares, 1)]
    return SimpleNamespace(titulares=titulares, catedras=catedras)
