import errno
import importlib.util
import json
from pathlib import Path
import ssl
from urllib.error import HTTPError, URLError

import pytest


ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('bootstrap_probe011', ROOT / 'preparar_entorno.py')
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


@pytest.mark.parametrize('error,code', [
    (URLError(TimeoutError('private-error-detail')), 'REGISTRY_TIMEOUT'),
    (URLError(ConnectionRefusedError('private-error-detail')), 'REGISTRY_CONNECTION_REFUSED'),
    (URLError(OSError(errno.ENETUNREACH, 'private-error-detail')), 'REGISTRY_ROUTE_UNAVAILABLE'),
    (URLError(ssl.SSLCertVerificationError(1, 'private-error-detail')), 'REGISTRY_CERTIFICATE_REJECTED'),
    (URLError(ssl.SSLError(1, 'private-error-detail')), 'REGISTRY_TLS_FAILED'),
    (HTTPError(bootstrap.ENDPOINT, 401, 'private-error-detail', {}, None), 'REGISTRY_AUTH_REJECTED'),
    (HTTPError(bootstrap.ENDPOINT, 302, 'private-error-detail', {}, None), 'REGISTRY_REDIRECT_REJECTED'),
    (HTTPError(bootstrap.ENDPOINT, 500, 'private-error-detail', {}, None), 'REGISTRY_HTTP_REJECTED'),
])
def test_closed_probe_errors_never_expose_credentials_or_raw_messages(monkeypatch, error, code):
    class Opener:
        def open(self, request, timeout):
            assert request.full_url == bootstrap.ENDPOINT + '/v2/'
            assert timeout == 5
            assert request.get_header('Authorization').startswith('Basic ')
            raise error
    monkeypatch.setattr(bootstrap, 'registry_opener', lambda _: Opener())
    result = bootstrap.probe_registry({'registry': {
        'ca_pem': 'fixture', 'username': 'nap011reader', 'password': 'do-not-copy-password'}})
    assert result['ok'] is False and result['code'] == code
    assert 'private-error-detail' not in json.dumps(result)
    assert 'do-not-copy-password' not in json.dumps(result)


def test_probe_success_closes_response_without_reading_private_body(monkeypatch):
    seen = []
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *_): seen.append('closed')
        def read(self): raise AssertionError('No se necesita leer el cuerpo')
    class Opener:
        def open(self, *_args, **_kwargs): return Response()
    monkeypatch.setattr(bootstrap, 'registry_opener', lambda _: Opener())
    result = bootstrap.probe_registry({'registry': {
        'ca_pem': 'fixture', 'username': 'nap011reader', 'password': 'do-not-copy-password'}})
    assert result == {'ok': True, 'code': 'REGISTRY_OK'}
    assert seen == ['closed']


def test_tcp_probe_is_fixed_target_and_closes_connection(monkeypatch):
    calls = []
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *_): calls.append('closed')
    def connect(target, *, timeout):
        calls.append((target, timeout))
        return Connection()
    monkeypatch.setattr(bootstrap.socket, 'create_connection', connect)
    assert bootstrap.probe_registry_tcp() == {'ok': True, 'code': 'REGISTRY_TCP_OK'}
    assert calls == [(('172.16.36.1', 5443), 3), 'closed']


def test_tcp_timeout_has_no_raw_network_error(monkeypatch):
    def connect(*_args, **_kwargs): raise TimeoutError('private-error-detail')
    monkeypatch.setattr(bootstrap.socket, 'create_connection', connect)
    assert bootstrap.probe_registry_tcp() == {'ok': False, 'code': 'REGISTRY_TIMEOUT'}


def test_diagnostic_cli_never_applies_node_configuration(tmp_path, monkeypatch, capsys):
    config = {'schema_version': 'nap-lab-bootstrap/1', 'registry': {
        'endpoint': bootstrap.ENDPOINT, 'ca_pem': 'fixture', 'username': 'nap011reader',
        'password': 'do-not-copy-password'}, 'network': {
            'cidr': '172.16.36.0/24', 'bridge': 'vmbr0', 'gateway': '172.16.36.2',
            'slots': [{'address': '172.16.36.81', 'mac': '02:11:00:00:00:81', 'host': 'app1.nap011.test'}]}}
    private = tmp_path / 'private.json'
    private.write_text(json.dumps(config)); private.chmod(0o600)
    monkeypatch.setattr('sys.argv', ['preparar_entorno.py', '--diagnose', '--config', str(private)])
    def forbidden(*_args, **_kwargs):
        raise AssertionError('El diagnóstico no puede aplicar cambios')
    monkeypatch.setattr(bootstrap, 'prepare_node', forbidden)
    monkeypatch.setattr(bootstrap, 'safe_directory', forbidden)
    monkeypatch.setattr(bootstrap.preflight, 'collect_node', lambda _: {'node': 'proxmox'})
    monkeypatch.setattr(bootstrap, 'probe_registry_tcp', lambda: {'ok': False, 'code': 'REGISTRY_TIMEOUT'})
    monkeypatch.setattr(bootstrap, 'probe_registry', forbidden)  # No insistir con TLS sin TCP.
    assert bootstrap.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result['state'] == 'bootstrap_diagnosed' and result['read_only'] is True
    assert result['registry']['code'] == 'REGISTRY_TIMEOUT'
    assert result['profiles_enabled'] == []
    assert 'do-not-copy-password' not in json.dumps(result)


def test_diagnostic_cannot_be_combined_with_apply(monkeypatch):
    monkeypatch.setattr('sys.argv', ['preparar_entorno.py', '--diagnose', '--apply'])
    with pytest.raises(SystemExit) as error:
        bootstrap.main()
    assert error.value.code == 2
