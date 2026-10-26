"""Programa fijo del guest de ensayo. Configuración sensible sólo por stdin."""

import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import Request, urlopen


PUBLIC_IMAGE = 'docker.io/traefik/whoami@sha256:4f90b33ddca9c4d4f06527070d6e503b16d71016edea036842be2a84e60c91cb'
PRIVATE_IMAGE = '172.16.36.1:5443/nap/campus-demo:acceptance'


def run(args, *, data=None, capture=False):
    result = subprocess.run(args, input=data, stdin=None if data is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        timeout=180, check=True)
    if capture:
        if len(result.stdout) > 65536: raise ValueError('OUTPUT_LIMIT')
        return result.stdout
    return b''


def require_blocked(host, port):
    try:
        with socket.create_connection((host, port), timeout=2):
            raise ValueError('ISOLATION_NOT_CONFIRMED')
    except OSError:
        pass


def note(method='GET', value=None):
    data = json.dumps(value).encode() if value is not None else None
    request = Request('http://127.0.0.1:8080/api/note', data=data,
                      headers={'Content-Type': 'application/json'}, method=method)
    with urlopen(request, timeout=2) as response:
        return json.load(response)


def ready():
    for _ in range(30):
        try:
            with urlopen('http://127.0.0.1:8080/health', timeout=1) as response:
                if response.status == 200: return
        except OSError: pass
        time.sleep(.2)
    raise ValueError('APPLICATION_NOT_READY')


def main():
    phase = 'prepare_runtime'
    try:
        raw = sys.stdin.buffer.read(65537)
        if len(raw) > 65536: raise ValueError('INPUT_LIMIT')
        registry = json.loads(raw)['registry']
        run(['systemctl', 'stop', 'docker.service', 'docker.socket'])
        override = Path('/etc/systemd/system/docker.service.d')
        override.mkdir(parents=True, exist_ok=True)
        (override / 'nap011-probe.conf').write_text('[Service]\nStandardOutput=null\nStandardError=null\n')
        docker_config = Path('/etc/docker')
        docker_config.mkdir(exist_ok=True)
        (docker_config / 'daemon.json').write_text(json.dumps({'log-driver': 'none', 'debug': False}))
        certificates = docker_config / 'certs.d/172.16.36.1:5443'
        certificates.mkdir(parents=True, exist_ok=True)
        (certificates / 'ca.crt').write_text(registry['ca_pem'])
        run(['systemctl', 'daemon-reload']); run(['systemctl', 'start', 'docker'])
        version = json.loads(run(['docker', 'version', '--format', '{{json .Server}}'], capture=True))
        phase = 'isolation'
        require_blocked('172.16.36.100', 8006)
        require_blocked('172.16.36.1', 8001)
        require_blocked('172.16.36.63', 443)
        phase = 'public_pull'
        run(['docker', 'pull', '--platform', 'linux/amd64', PUBLIC_IMAGE])
        phase = 'private_pull'
        with tempfile.TemporaryDirectory(prefix='nap011-auth-', dir='/run') as authentication:
            run(['docker', '--config', authentication, 'login', '172.16.36.1:5443',
                 '--username', registry['username'], '--password-stdin'], data=(registry['password']+'\n').encode())
            run(['docker', '--config', authentication, 'pull', '--platform', 'linux/amd64', PRIVATE_IMAGE])
        digests = json.loads(run(['docker', 'image', 'inspect', PRIVATE_IMAGE, '--format', '{{json .RepoDigests}}'], capture=True))
        frozen_image = next(d for d in digests if d.startswith('172.16.36.1:5443/nap/campus-demo@sha256:'))
        # No configuración de registry ni valores privados en el container de aplicación.
        registry.clear(); del raw
        phase = 'application'
        run(['docker', 'volume', 'create', 'nap011-demo-data'])
        run(['docker', 'run', '-d', '--name', 'nap011-demo', '--read-only', '--cap-drop', 'ALL',
             '--security-opt', 'no-new-privileges', '--log-driver', 'none', '--no-healthcheck',
             '--pids-limit', '64', '--memory', '256m', '--cpus', '1',
             '--mount', 'type=volume,source=nap011-demo-data,target=/data',
             '--publish', '8080:8080', frozen_image])
        ready(); note('POST', {'note': 'Persistencia 011 en LXC'})
        run(['docker', 'restart', 'nap011-demo']); ready()
        if note()['note'] != 'Persistencia 011 en LXC': raise ValueError('PERSISTENCE_NOT_CONFIRMED')
        config = json.loads(run(['docker', 'inspect', 'nap011-demo'], capture=True))[0]
        if config['HostConfig']['LogConfig']['Type'] != 'none' or config['Config']['User'] != '10001:10001':
            raise ValueError('APP_POLICY_NOT_CONFIRMED')
        security = json.loads(run(['docker', 'info', '--format', '{{json .SecurityOptions}}'], capture=True))
        if (not any('name=seccomp' in v for v in security) or not any('name=apparmor' in v for v in security)
                or config.get('AppArmorProfile') in {None, '', 'unconfined'}):
            raise ValueError('APP_POLICY_NOT_CONFIRMED')
        disk = int(run(['df', '--output=used', '-B1', '/'], capture=True).decode().splitlines()[-1])
        peak = int(Path('/sys/fs/cgroup/memory.peak').read_text())
        if disk > 8*1024**3 or peak > 1024**3: raise ValueError('MEDIUM_NOT_CONFIRMED')
        result = {'state': 'guest_probe_passed', 'public_pull': True, 'private_pull': True,
                  'native_restart_persistence': True, 'credential_file_removed':
                  not any(Path('/run').glob('nap011-auth-*')), 'managed_endpoints_blocked': True,
                  'runtime_version': version['Version'], 'disk_used_bytes': disk, 'memory_peak_bytes': peak}
        result['private_image_digest'] = frozen_image.split('@', 1)[1]
    except (OSError, ValueError, KeyError, StopIteration, subprocess.SubprocessError):
        result = {'state': 'guest_probe_failed', 'phase': phase}
    print(json.dumps(result))


if __name__ == '__main__':
    main()
