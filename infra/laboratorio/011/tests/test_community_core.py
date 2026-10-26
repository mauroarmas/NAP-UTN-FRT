"""Core real fijado, en Docker sin red/capabilities; no acredita LXC ni aplicaciones."""

import json
import importlib.util
import os
from pathlib import Path
import subprocess

import pytest


@pytest.mark.integration
def test_pinned_core_loads_locally_without_network_or_raw_output():
    cache = os.environ.get('NAP011_COMMUNITY_SOURCE_CACHE')
    if not cache: pytest.skip('Requiere cache de fuentes fijadas y verificada')
    source = Path(__file__).parents[1].resolve()
    result = subprocess.run(['docker', 'run', '--rm', '--user', '1000:1000', '--network', 'none',
        '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--log-driver', 'none',
        '--tmpfs', '/tmp:rw,nosuid,noexec,size=8m',
        '--tmpfs', '/usr/local/community-scripts:rw,nosuid,noexec,uid=1000,gid=1000,mode=0700,size=1m',
        '--mount', f'type=bind,source={Path(cache).resolve()},target=/in,readonly',
        '--mount', f'type=bind,source={source},target=/nap,readonly',
        '--env', 'NAP_BUNDLE_ROOT=/in', 'nap011-harness-check:lab', '/nap/community_harness.sh', '--check-only'],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, f'Core bootstrap no confirmado, exit={result.returncode}'
    assert result.stderr == ''
    assert json.loads(result.stdout) == {'state': 'core_bootstrap_loaded', 'profiles_enabled': [],
                                         'real_guest_gate_pending': True}


@pytest.mark.integration
def test_core_keeps_frozen_multistanza_distro_sources(tmp_path):
    cache = os.environ.get('NAP011_COMMUNITY_SOURCE_CACHE')
    if not cache: pytest.skip('Requiere cache de fuentes fijadas y verificada')
    source = Path(__file__).parents[1].resolve()
    s = importlib.util.spec_from_file_location('core_guard_regression', source / 'community_guard.py')
    guard = importlib.util.module_from_spec(s); s.loader.exec_module(guard)
    plan = json.loads((source / 'community-dependencies.lock.json').read_text())
    snapshot = tmp_path / 'fixture.sources'; snapshot.write_text(guard.apt_sources(plan)); snapshot.chmod(0o600)
    program = 'cp /fixture.sources /etc/apt/sources.list.d/"$1"; source /nap/community_harness.sh --check-only; cleanup_orphaned_sources; test -f /etc/apt/sources.list.d/"$1"'
    result = subprocess.run(['docker', 'run', '--rm', '--user', '1000:1000', '--network', 'none',
        '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--log-driver', 'none',
        '--tmpfs', '/tmp:rw,nosuid,noexec,size=8m',
        '--tmpfs', '/usr/local/community-scripts:rw,nosuid,noexec,uid=1000,gid=1000,mode=0700,size=1m',
        '--tmpfs', '/etc/apt/sources.list.d:rw,nosuid,noexec,uid=1000,gid=1000,mode=0700,size=1m',
        '--mount', f'type=bind,source={snapshot},target=/fixture.sources,readonly',
        '--mount', f'type=bind,source={Path(cache).resolve()},target=/in,readonly',
        '--mount', f'type=bind,source={source},target=/nap,readonly', '--env', 'NAP_BUNDLE_ROOT=/in',
        'nap011-harness-check:lab', '-c', program, 'core-regression', guard.APT_SOURCE_FILE],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, 'El helper no debe eliminar el repositorio congelado'
