import importlib.util
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('registry_lab011', ROOT / 'registry_lab.py')
registry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(registry)


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
