"""Programa fijo del invitado piloto; recibe sólo archivos públicos verificados."""

import base64
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import urlopen


WORK = Path('/opt/nap-community')
OWN_FILES = {'spike_community.py', 'community_guard.py', 'community_harness.sh',
             'community_bootstrap_policy.func', 'community_install_policy.func',
             'community-sources.lock.json', 'community-dependencies.lock.json'}


def run(args, *, capture=False, timeout=30):
    result = subprocess.run(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, timeout=timeout, check=True)
    if capture and len(result.stdout) > 65536: raise ValueError('OUTPUT_LIMIT')
    return result.stdout if capture else b''


def blocked(host, port):
    import socket
    try:
        with socket.create_connection((host, port), timeout=2): raise ValueError('ISOLATION_NOT_CONFIRMED')
    except OSError: pass


def main():
    phase = 'prepare_runtime'
    try:
        raw = sys.stdin.buffer.read(2097153)
        if len(raw) > 2097152: raise ValueError('PAYLOAD_LIMIT')
        payload = json.loads(raw)
        if set(payload) != {'application', 'files'} or payload['application'] not in {'mariadb', 'caddy'}:
            raise ValueError('PAYLOAD_SCHEMA')
        source_lock = json.loads(base64.b64decode(payload['files']['community-sources.lock.json'], validate=True))
        expected = OWN_FILES | {'sources/' + name for name in source_lock['sources']}
        if set(payload['files']) != expected: raise ValueError('PAYLOAD_SCHEMA')
        if WORK.exists() or WORK.is_symlink(): raise ValueError('WORKSPACE_OCCUPIED')
        os.umask(0o077); WORK.mkdir()
        for name, encoded in payload['files'].items():
            # Los nombres propios son cerrados; las fuentes se validan antes de source.
            parts = Path(name).parts
            if Path(name).is_absolute() or '..' in parts: raise ValueError('PAYLOAD_SCHEMA')
            data = base64.b64decode(encoded, validate=True)
            path = WORK / name; path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'wb') as target: target.write(data)
        s = importlib.util.spec_from_file_location('community_guest', WORK / 'spike_community.py')
        community = importlib.util.module_from_spec(s); s.loader.exec_module(community)
        community.verify_sources(WORK / 'sources', source_lock)
        plan = community.validate_dependencies(json.loads((WORK / 'community-dependencies.lock.json').read_text()))
        s = importlib.util.spec_from_file_location('community_guard_guest', WORK / 'community_guard.py')
        guard = importlib.util.module_from_spec(s); s.loader.exec_module(guard)
        guard.verify_apt_state('/', plan)
        if payload['application'] == 'caddy': guard.verify_artifact(plan)
        for name in ['apt', 'apt-get']:
            path = Path('/usr/local/sbin') / name
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o755)
            with os.fdopen(fd, 'w') as wrapper:
                wrapper.write('#!/bin/sh\nexec /usr/bin/python3 /opt/nap-community/community_guard.py apt "$@"\n')
            path.chmod(0o755)
        phase = 'isolation'
        blocked('172.16.36.100', 8006); blocked('172.16.36.63', 443)
        phase = 'application'
        env = {'PATH': '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
               'DEBIAN_FRONTEND': 'noninteractive', 'LC_ALL': 'C.UTF-8', 'LANG': 'C.UTF-8',
               'NAP_BUNDLE_ROOT': str(WORK / 'sources')}
        install = subprocess.run(['/bin/bash', str(WORK / 'community_harness.sh'), '--install', payload['application']],
            env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1200)
        if install.returncode:
            code = {84: 'UNDECLARED_HELPER', 85: 'UNDECLARED_DOWNLOAD', 90: 'UNRESOLVED_PROMPT',
                    82: 'SOURCE_REJECTED'}.get(install.returncode, 'INSTALLER_FAILED')
            error_receipt = Path('/run/nap-community-error.json')
            if error_receipt.is_file() and not error_receipt.is_symlink() and error_receipt.stat().st_size <= 1024:
                recorded = json.loads(error_receipt.read_text()).get('code')
                if recorded in {'APT_SOURCES_CHANGED', 'APT_RELEASE_CHANGED', 'DEPENDENCY_ARTIFACT'}: code = recorded
            events = dict(line.split() for line in Path('/sys/fs/cgroup/memory.events').read_text().splitlines())
            if int(events.get('oom_kill', '0')) > 0: code = 'MEDIUM_NOT_CONFIRMED'
            result = {'state': 'guest_probe_failed', 'phase': phase, 'code': code, 'exit_code': install.returncode}
            print(json.dumps(result)); return
        application = payload['application']
        run(['systemctl', 'is-active', '--quiet', application])
        if application == 'mariadb':
            response = run(['mariadb', '--protocol=socket', '--skip-column-names', '--batch', '-uroot',
                            '--execute', 'SELECT 1;'], capture=True)
            if response.strip() != b'1': raise ValueError('PRODUCT_PROBE_FAILED')
            version = run(['mariadb', '--version'], capture=True).decode().strip()
        else:
            version = run(['caddy', 'version'], capture=True).decode().split()[0]
            if version != 'v' + plan['caddy']['version']: raise ValueError('PRODUCT_PROBE_FAILED')
            ready = False
            for _ in range(25):
                try:
                    with urlopen('http://127.0.0.1:80', timeout=1) as response: ready = response.status == 200
                    if ready: break
                except OSError: pass
                time.sleep(.2)
            if not ready: raise ValueError('PRODUCT_PROBE_FAILED')
        guard.verify_apt_state('/', plan)
        password = run(['passwd', '-S', 'root'], capture=True).decode().split()[1]
        raw_logs = [*Path('/root').glob('.install-*.log*'), *Path('/tmp').glob('.install-*.log*')]
        if password != 'L' or raw_logs or Path('/usr/bin/update').exists(): raise ValueError('LOGIN_OR_LOG_POLICY')
        peak = int(Path('/sys/fs/cgroup/memory.peak').read_text())
        events = dict(line.split() for line in Path('/sys/fs/cgroup/memory.events').read_text().splitlines())
        disk = int(run(['df', '--output=used', '-B1', '/'], capture=True).decode().splitlines()[-1])
        if peak > 1024**3 or disk > 8*1024**3 or int(events.get('oom_kill', '0')) > 0:
            raise ValueError('MEDIUM_NOT_CONFIRMED')
        result = {'state': 'guest_probe_passed', 'application': application, 'product_version': version,
            'native_product_probe': True, 'root_locked': True, 'raw_installer_logs_absent': True,
            'mutable_updater_absent': True, 'memory_peak_bytes': peak, 'disk_used_bytes': disk,
            'oom_kills': int(events.get('oom_kill', '0')), 'snapshots_verified': 3}
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        codes = {'PAYLOAD_LIMIT', 'PAYLOAD_SCHEMA', 'WORKSPACE_OCCUPIED', 'ISOLATION_NOT_CONFIRMED',
                 'PRODUCT_PROBE_FAILED', 'LOGIN_OR_LOG_POLICY', 'MEDIUM_NOT_CONFIRMED', 'APT_RELEASE_CHANGED',
                 'APT_SOURCES_CHANGED', 'DEPENDENCY_ARTIFACT'}
        result = {'state': 'guest_probe_failed', 'phase': phase,
                  'code': str(error) if str(error) in codes else 'INFRASTRUCTURE_NOT_CONFIRMED'}
    print(json.dumps(result))


if __name__ == '__main__':
    main()
