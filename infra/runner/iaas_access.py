"""Acceso SSH a un Linux IaaS: crea el usuario `nap`, instala una clave y endurece sshd.

Protocolo `nap-iaas-access/1`. Solo biblioteca estándar. La clave pública viaja por stdin a un
`pct exec` con rutas fijas: nunca se interpola en una línea de comandos ni en un registro.
No modifica `node_executor.py` (entra en el policy_digest del motor Docker).
"""
from datetime import datetime, timezone
import hashlib
import ipaddress
import os
from pathlib import Path
import time

if __package__:
    from app.schemas.guest_runner import RunnerError, parse_json
    from app.schemas.iaas_access import PROTOCOL, USUARIO, parse_request
    from app.utils.ssh_keys import ClaveSshInvalida, validar_clave
    from infra.runner.node_executor import bounded_command, parse_system_json
else:
    from protocol import RunnerError, parse_json
    from iaas_protocol import PROTOCOL, USUARIO, parse_request
    from ssh_keys import ClaveSshInvalida, validar_clave
    from node_executor import bounded_command, parse_system_json


PCT = '/usr/sbin/pct'
HOME = '/home/' + USUARIO
AUTHORIZED = HOME + '/.ssh/authorized_keys'
SUDOERS = '/etc/sudoers.d/nap-acceso'
SSHD_DROPIN = '/etc/ssh/sshd_config.d/00-nap-acceso.conf'
SUDOERS_CONTENIDO = USUARIO + ' ALL=(ALL) NOPASSWD:ALL\n'
# 00- gana sobre otros archivos (sshd usa el primer valor): un 50-cloud-init con PasswordAuthentication yes no lo anula.
SSHD_CONTENIDO = ('# Gestionado por NAP; no editar.\nPasswordAuthentication no\nKbdInteractiveAuthentication no\n'
    'PermitRootLogin no\nPubkeyAuthentication yes\nAllowUsers ' + USUARIO + '\n')
# Código constante: recibe sólo rutas/modos fijados aquí; el contenido llega por stdin.
ESCRIBIR = 'set -e; umask 077; cat > "$1.nap-new"; chmod "$2" "$1.nap-new"; chown "$3" "$1.nap-new"; mv "$1.nap-new" "$1"'
DIRECCION = 'ip -4 -o addr show dev eth0 scope global'
BANNER = 'exec 3<>/dev/tcp/127.0.0.1/22 && IFS= read -r -t 5 linea <&3 && printf "%s" "${linea:0:8}"'
SIN_EFECTO = {'IDENTITY_MISMATCH', 'GUEST_NOT_RUNNING', 'SSHD_UNAVAILABLE', 'SUDO_UNAVAILABLE', 'INVALID_REQUEST'}


class IaasAccessExecutor:
    def __init__(self, *, run_command=None, local_node=None, sleep=time.sleep):
        self.run_command, self.sleep = run_command or bounded_command, sleep
        self.local_node = local_node or Path(os.readlink('/etc/pve/local')).name
        self.deadline = time.monotonic() + 100
        self.effect = False

    def _run(self, argv, *, input=None, accepted=(0,)):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise RunnerError('DEADLINE_EXCEEDED')
        return self.run_command(argv, input=input, timeout=min(remaining, 60), accepted_codes=accepted)

    def verify(self, request):
        """Identidad completa antes y después de cada efecto; un vmid reutilizado falla cerrado."""
        if request['node'] != self.local_node:
            raise RunnerError('IDENTITY_MISMATCH')
        resources = parse_system_json(self._run(['/usr/bin/pvesh', 'get', '/cluster/resources', '--type', 'vm',
            '--output-format', 'json']), limit=2097152)
        matches = [row for row in resources if row.get('vmid') == request['vmid']]
        if (len(matches) != 1 or matches[0].get('node') != request['node'] or matches[0].get('type') != 'lxc'
            or matches[0].get('pool') != request['pool']):
            raise RunnerError('IDENTITY_MISMATCH')
        config = parse_system_json(self._run(['/usr/bin/pvesh', 'get',
            '/nodes/' + request['node'] + '/lxc/' + str(request['vmid']) + '/config', '--output-format', 'json']))
        try:
            marker = parse_json(config['description'].encode())['nap']
            expected = {'resource_uuid': request['resource_uuid'], 'pool': request['pool'],
                'nonce_sha256': hashlib.sha256(request['nonce'].encode()).hexdigest()}
            unprivileged = config.get('unprivileged')
            if marker != expected or not (unprivileged is True or type(unprivileged) is int and unprivileged == 1):
                raise ValueError()
        except (ValueError, KeyError, TypeError, AttributeError, RunnerError):
            raise RunnerError('IDENTITY_MISMATCH') from None

    def _exec(self, request, argv, *, input=None, accepted=(0,)):
        return self._run([PCT, 'exec', str(request['vmid']), '--', *argv], input=input, accepted=accepted)

    def _write(self, request, path, content, mode, owner):
        self.effect = True
        self._exec(request, ['/bin/sh', '-c', ESCRIBIR, 'nap-escribir', path, mode, owner], input=content.encode())

    def _running(self, request):
        return b'status: running' in self._run([PCT, 'status', str(request['vmid'])])

    def _present(self, request, path):
        return bool(self._exec(request, ['/bin/sh', '-c', 'test -x "$1" && echo si', 'nap-test', path], accepted=(0, 1)).strip())

    def direccion(self, request):
        """IPv4 que el contenedor tiene realmente en eth0 (puede diferir de la reservada si el DHCP no la respeta)."""
        salida = self._exec(request, ['/bin/sh', '-c', DIRECCION], accepted=(0, 1, 2)).decode(errors='replace')
        for linea in salida.splitlines():
            partes = linea.split()
            if 'inet' in partes and partes.index('inet') + 1 < len(partes):
                try:
                    return str(ipaddress.IPv4Address(partes[partes.index('inet') + 1].split('/')[0]))
                except ValueError:
                    continue
        return None

    def configure(self, request):
        if not self._running(request):
            raise RunnerError('GUEST_NOT_RUNNING')
        if not self._present(request, '/usr/sbin/sshd'):
            raise RunnerError('SSHD_UNAVAILABLE')
        if not self._present(request, '/usr/bin/sudo'):
            raise RunnerError('SUDO_UNAVAILABLE')
        if not self._exec(request, ['/usr/bin/getent', 'passwd', USUARIO], accepted=(0, 2)).strip():
            self.effect = True
            self._exec(request, ['/usr/sbin/useradd', '-m', '-s', '/bin/bash', USUARIO])
        # '*' (no '!'): la cuenta no tiene contraseña válida, pero sshd no la trata como bloqueada.
        self._exec(request, ['/usr/sbin/usermod', '-p', '*', USUARIO])
        self._exec(request, ['/usr/bin/install', '-d', '-m', '700', '-o', USUARIO, '-g', USUARIO, HOME + '/.ssh'])
        self._write(request, AUTHORIZED, request['clave_publica'] + '\n', '600', USUARIO + ':' + USUARIO)
        self._write(request, SUDOERS, SUDOERS_CONTENIDO, '440', 'root:root')
        self._write(request, SSHD_DROPIN, SSHD_CONTENIDO, '644', 'root:root')
        self._exec(request, ['/usr/sbin/sshd', '-t'])
        self._exec(request, ['/usr/bin/systemctl', 'enable', 'ssh'])
        self._exec(request, ['/usr/bin/systemctl', 'restart', 'ssh'])
        self.verify(request)
        return self.probe(request, reintentos=5)

    def probe(self, request, *, reintentos=1):
        if not self._running(request):
            raise RunnerError('GUEST_NOT_RUNNING')
        if not self._exec(request, ['/usr/bin/getent', 'passwd', USUARIO], accepted=(0, 2)).strip():
            raise RunnerError('PROBE_FAILED')
        lines = [row for row in self._exec(request, ['/bin/cat', AUTHORIZED], accepted=(0, 1)).decode(errors='replace').splitlines() if row.strip()]
        try:
            if len(lines) != 1 or validar_clave(lines[0])[2] != request['huella']:
                raise RunnerError('PROBE_FAILED')
        except ClaveSshInvalida:
            raise RunnerError('PROBE_FAILED') from None
        efectivo = {row.strip().lower() for row in self._exec(request, ['/usr/sbin/sshd', '-T']).decode(errors='replace').splitlines()}
        if not {'passwordauthentication no', 'permitrootlogin no', 'pubkeyauthentication yes', 'allowusers ' + USUARIO} <= efectivo:
            raise RunnerError('PROBE_FAILED')
        for intento in range(reintentos):
            if self._exec(request, ['/bin/bash', '-c', BANNER], accepted=(0, 1)).startswith(b'SSH-2.0-'):
                resultado = {'ready': True, 'revision': request['revision'], 'huella': request['huella'],
                    'usuario': USUARIO, 'puerto': 22}
                direccion = self.direccion(request)
                if direccion:
                    resultado['direccion'] = direccion
                return resultado
            if intento + 1 < reintentos:
                self.sleep(1)
        raise RunnerError('PROBE_FAILED')


def _response(request, *, status, phase, identity, result=None, code=None):
    value = {key: request[key] for key in ['protocol', 'operation_id', 'action', 'resource_uuid']}
    value.update(status=status, phase=phase, identity_verified=identity, observed_at=datetime.now(timezone.utc).isoformat())
    if result is not None:
        value['result'] = result
    else:
        value['error'] = {'code': code or 'UNCONFIRMED', 'phase': phase, 'retryable': status in {'failed', 'unconfirmed'}
            and code not in {'INVALID_REQUEST', 'IDENTITY_MISMATCH', 'SSHD_UNAVAILABLE', 'SUDO_UNAVAILABLE'}}
    return value


def handle_iaas_access_request(raw, *, executor=None):
    request = {'protocol': PROTOCOL, 'operation_id': '00000000-0000-0000-0000-000000000000',
        'action': 'probe', 'resource_uuid': '00000000-0000-0000-0000-000000000000'}
    identity, phase = False, 'validation'
    try:
        request = parse_request(raw)
        executor = executor or IaasAccessExecutor()
        phase = 'identity'
        executor.verify(request)
        identity, phase = True, 'execution'
        result = executor.configure(request) if request['action'] == 'configure' else executor.probe(request, reintentos=6)
        return _response(request, status='succeeded', phase='verified', identity=True, result=result)
    except RunnerError as exc:
        # Sin efecto aplicado el fallo es definitivo; con efecto el resultado queda sin confirmar.
        effect = bool(executor and executor.effect) and exc.code not in SIN_EFECTO
        status = 'unconfirmed' if effect or exc.code == 'UNCONFIRMED' else 'failed'
        return _response(request, status=status, phase=phase, identity=identity and exc.code != 'IDENTITY_MISMATCH', code=exc.code)
    except Exception:
        return _response(request, status='unconfirmed', phase=phase, identity=False, code='UNCONFIRMED')


def is_iaas_access_request(raw):
    """Despacho explícito por protocolo; nunca ejecuta nada que provenga del cliente."""
    try:
        value = parse_json(raw, limit=16384)
        return isinstance(value, dict) and value.get('protocol') == PROTOCOL
    except Exception:
        return False
