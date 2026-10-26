import importlib.util
from pathlib import Path
import subprocess
import ssl

import pytest


ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('registry_lab011', ROOT / 'registry_lab.py')
registry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(registry)


def test_generated_chain_passes_strict_tls_without_network(tmp_path):
    """Misma validación estricta de Python 3.13/OpenSSL, usando BIO en memoria."""
    root = tmp_path / 'registry'
    registry.create_credentials(root)
    client_context = ssl.create_default_context(cafile=str(root / 'pki/ca.crt'))
    client_context.verify_flags |= ssl.VERIFY_X509_STRICT
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(root / 'pki/server.crt', root / 'pki/server.key')
    incoming_client, outgoing_client = ssl.MemoryBIO(), ssl.MemoryBIO()
    incoming_server, outgoing_server = ssl.MemoryBIO(), ssl.MemoryBIO()
    client = client_context.wrap_bio(incoming_client, outgoing_client, server_hostname='172.16.36.1')
    server = server_context.wrap_bio(incoming_server, outgoing_server, server_side=True)
    done = set()
    for _ in range(20):
        for name, endpoint in [('client', client), ('server', server)]:
            if name in done:
                continue
            try:
                endpoint.do_handshake(); done.add(name)
            except ssl.SSLWantReadError:
                pass
        if outgoing_client.pending:
            incoming_server.write(outgoing_client.read())
        if outgoing_server.pending:
            incoming_client.write(outgoing_server.read())
        if len(done) == 2:
            break
    assert done == {'client', 'server'}
    assert client.getpeercert()['subjectAltName'] == (('IP Address', '172.16.36.1'),)


def test_registry_plan_does_not_create_secrets_or_docker_resources(tmp_path):
    path = tmp_path / 'registry'
    result = registry.prepare(path)
    assert not path.exists()
    assert result['state'] == 'plan_without_changes'
    assert result['profiles_enabled'] == []


def test_registry_never_mounts_ca_private_key_or_publisher_authfile(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(registry, 'owned_container', lambda: False)
    monkeypatch.setattr(registry, 'docker', lambda *args: calls.append(args))
    registry.run_registry(tmp_path, readonly=True)
    args = tuple(map(str, calls[0]))
    mounts = [args[index + 1] for index, arg in enumerate(args) if arg == '--mount']
    assert all('ca.key' not in mount and 'publisher.json' not in mount for mount in mounts)
    assert not any('target=/pki,' in mount or 'target=/auth,' in mount for mount in mounts)
    assert args[args.index('--log-driver') + 1] == 'none'
    assert args[args.index('--cap-drop') + 1] == 'ALL'


def test_publication_failure_always_restores_read_only_mode(tmp_path, monkeypatch):
    path = tmp_path / 'registry'
    path.mkdir(mode=0o700)
    modes = []
    monkeypatch.setattr(registry, 'run_registry', lambda _, readonly: modes.append(readonly))
    monkeypatch.setattr(registry, 'verify', lambda _, readonly: None)
    def docker(*args):
        if args[0] == 'save':
            Path(args[2]).write_bytes(b'archive-fixture')
        else:
            raise subprocess.CalledProcessError(1, ['copy-fixture'])
        return ''
    monkeypatch.setattr(registry, 'docker', docker)
    with pytest.raises(subprocess.CalledProcessError):
        registry.prepare(path, apply=True)
    assert modes == [False, True]
    assert not (path / 'campus-demo.tar').exists()
    assert not (path / 'complete.json').exists()
