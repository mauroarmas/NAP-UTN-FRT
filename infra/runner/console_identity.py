"""Identidades individuales de consola (feature 022): crear/actualizar, retirar, terminar sesiones y comprobar.

Protocolo `nap-console-identity/1`. Sólo biblioteca estándar. Acciones CERRADAS: rutas y argumentos fijos, nombres y
pools validados por el protocolo; la contraseña llega por stdin a `pveum passwd` y nunca va en `argv`, en respuestas
ni en registros. Sólo concede el rol `NapConsola` sobre pools de cátedra; no hay otro permiso posible.
No modifica `node_executor.py` ni nada que entre en el policy_digest del motor Docker.
"""
from datetime import datetime, timezone
import json
import re
import time

if __package__:
    from app.schemas.guest_runner import RunnerError, parse_json
    from app.schemas.console_identity import PROTOCOL, ROL, parse_request
    from infra.runner.node_executor import bounded_command
else:
    from protocol import RunnerError, parse_json
    from console_identity_protocol import PROTOCOL, ROL, parse_request
    from node_executor import bounded_command


PVEUM = '/usr/sbin/pveum'
PVESH = '/usr/bin/pvesh'
PGREP = '/usr/bin/pgrep'
PKILL = '/usr/bin/pkill'
RUNNER_CONFIG = '/etc/nap/applications-011/runner.json'
PRIVS_ROL = {'VM.Console', 'VM.Audit'}
COMENTARIO = 'Consola NAP (identidad gestionada) r'
SIN_EFECTO = {'IDENTITY_MISMATCH', 'ROLE_UNAVAILABLE', 'INVALID_REQUEST'}
_ACL_PATH = re.compile(r'/pool/(catedra-[0-9]{1,9})')


def _cluster_del_nodo():
    try:
        with open(RUNNER_CONFIG, 'rb') as fh:
            return parse_json(fh.read(1048577), limit=1048576)['cluster_uuid']
    except (OSError, KeyError, TypeError, RunnerError):
        return None


class ConsoleIdentityExecutor:
    def __init__(self, *, run_command=None, cluster_uuid=None, now=time.monotonic):
        self.run_command = run_command or bounded_command
        self.cluster_uuid = cluster_uuid or _cluster_del_nodo
        self.now = now
        self.deadline = now() + 100
        self.effect = False

    def _run(self, argv, *, input=None, accepted=(0,)):
        remaining = self.deadline - self.now()
        if remaining <= 0:
            raise RunnerError('DEADLINE_EXCEEDED')
        return self.run_command(argv, input=input, timeout=min(remaining, 60), accepted_codes=accepted)

    def _json(self, argv):
        try:
            return json.loads(self._run(argv).decode())
        except (ValueError, UnicodeError):
            raise RunnerError('UNCONFIRMED') from None

    # -- lectura ------------------------------------------------------------------------------------------------------
    def verify(self, request):
        cluster = self.cluster_uuid() if callable(self.cluster_uuid) else self.cluster_uuid
        if cluster != request['cluster_uuid']:
            raise RunnerError('IDENTITY_MISMATCH')
        roles = {fila['roleid']: set((fila.get('privs') or '').split(',')) - {''} for fila in self._json(
            [PVEUM, 'role', 'list', '--output-format', 'json'])}
        if roles.get(ROL) != PRIVS_ROL:
            raise RunnerError('ROLE_UNAVAILABLE')

    def _usuario(self, identidad):
        for fila in self._json([PVEUM, 'user', 'list', '--output-format', 'json']):
            if fila.get('userid') == identidad:
                return fila
        return None

    def _acls(self, identidad):
        """ACL de ESTA identidad: [(path, roleid)]."""
        return [(fila['path'], fila['roleid']) for fila in self._json([PVEUM, 'acl', 'list', '--output-format', 'json'])
                if fila.get('type') == 'user' and fila.get('ugid') == identidad]

    def _pools_existentes(self):
        return {fila['poolid'] for fila in self._json([PVESH, 'get', '/pools', '--output-format', 'json'])}

    def _pools_con_rol(self, identidad):
        return sorted({m.group(1) for path, rol in self._acls(identidad) if rol == ROL and (m := _ACL_PATH.fullmatch(path))})

    # -- acciones -----------------------------------------------------------------------------------------------------
    def ensure(self, request):
        identidad, pools = request['identidad'], list(request['pools'])
        existente = self._usuario(identidad)
        creada = existente is None
        rev = COMENTARIO + str(request['revision'])
        password = 'sin_cambios'
        if creada:
            self.effect = True
            self._run([PVEUM, 'user', 'add', identidad, '--comment', rev])
        if creada or (existente.get('comment') or '') != rev:
            self.effect = True
            # Contraseña por stdin, dos veces; nunca en argv.
            clave = request['password_consola']
            self._run([PVEUM, 'passwd', identidad], input=(clave + '\n' + clave + '\n').encode())
            self._run([PVEUM, 'user', 'modify', identidad, '--comment', rev])
            password = 'aplicada'
        existentes = self._pools_existentes()
        deseados = [p for p in pools if p in existentes]
        pendientes = [p for p in pools if p not in existentes]
        # Quitar cualquier ACL de esta identidad que no sea el rol de consola sobre un pool deseado.
        for path, rol in self._acls(identidad):
            m = _ACL_PATH.fullmatch(path)
            if not (rol == ROL and m and m.group(1) in deseados):
                self.effect = True
                self._run([PVEUM, 'acl', 'delete', path, '--users', identidad, '--roles', rol])
        for pool in deseados:
            if pool not in self._pools_con_rol(identidad):
                self.effect = True
                self._run([PVEUM, 'acl', 'modify', '/pool/' + pool, '--users', identidad, '--roles', ROL])
        aplicados = self._pools_con_rol(identidad)
        if aplicados != sorted(deseados):
            raise RunnerError('PROBE_FAILED')
        return {'pools_aplicados': aplicados, 'pools_pendientes': sorted(pendientes), 'creada': creada, 'password': password}

    def retire(self, request):
        identidad = request['identidad']
        if self._usuario(identidad) is None:
            return {'retirada': True, 'pools_quitados': []}
        quitados = []
        if 'pools' in request:
            for pool in request['pools']:
                if pool in self._pools_con_rol(identidad):
                    self.effect = True
                    self._run([PVEUM, 'acl', 'delete', '/pool/' + pool, '--users', identidad, '--roles', ROL])
                    quitados.append(pool)
            if any(pool in self._pools_con_rol(identidad) for pool in request['pools']):
                raise RunnerError('PROBE_FAILED')
            return {'retirada': False, 'pools_quitados': sorted(quitados)}
        for path, rol in self._acls(identidad):
            self.effect = True
            if (m := _ACL_PATH.fullmatch(path)) and rol == ROL:
                quitados.append(m.group(1))
            self._run([PVEUM, 'acl', 'delete', path, '--users', identidad, '--roles', rol])
        self.effect = True
        self._run([PVEUM, 'user', 'delete', identidad])
        if self._usuario(identidad) is not None:
            raise RunnerError('PROBE_FAILED')
        return {'retirada': True, 'pools_quitados': sorted(set(quitados))}

    def end_sessions(self, request):
        terminadas = 0
        for vmid in request['vmids']:
            patron = 'termproxy .*--path /vms/' + str(int(vmid)) + '( |$)'
            salida = self._run([PGREP, '-f', patron], accepted=(0, 1)).decode(errors='replace')
            cantidad = len([l for l in salida.split() if l.strip()])
            if cantidad:
                self.effect = True
                self._run([PKILL, '-f', patron], accepted=(0, 1))
                terminadas += cantidad
        return {'terminadas': terminadas}

    def probe(self, request):
        identidad = request['identidad']
        existe = self._usuario(identidad) is not None
        pools = self._pools_con_rol(identidad) if existe else []
        return {'existe': existe, 'pools': pools, 'roles': [ROL] if pools else []}


def _response(request, *, status, phase, identity, result=None, code=None):
    value = {key: request[key] for key in ['protocol', 'operation_id', 'action', 'identidad']}
    value.update(status=status, phase=phase, identity_verified=identity, observed_at=datetime.now(timezone.utc).isoformat())
    if result is not None:
        value['result'] = result
    else:
        value['error'] = {'code': code or 'UNCONFIRMED', 'phase': phase,
                          'retryable': status in {'failed', 'unconfirmed'} and code not in SIN_EFECTO}
    return value


def handle_console_identity_request(raw, *, executor=None):
    request = {'protocol': PROTOCOL, 'operation_id': '00000000-0000-0000-0000-000000000000', 'action': 'probe',
        'identidad': 'nap-u0@pve'}
    identity, phase = False, 'validation'
    try:
        request = parse_request(raw)
        executor = executor or ConsoleIdentityExecutor()
        phase = 'identity'
        executor.verify(request)
        identity, phase = True, 'execution'
        result = getattr(executor, request['action'])(request)
        return _response(request, status='succeeded', phase='verified', identity=True, result=result)
    except RunnerError as exc:
        # Sin efecto aplicado el fallo es definitivo; con efecto el resultado queda sin confirmar.
        effect = bool(executor and executor.effect) and exc.code not in SIN_EFECTO
        status = 'unconfirmed' if effect or exc.code == 'UNCONFIRMED' else 'failed'
        return _response(request, status=status, phase=phase, identity=identity and exc.code != 'IDENTITY_MISMATCH', code=exc.code)
    except Exception:
        return _response(request, status='unconfirmed', phase=phase, identity=False, code='UNCONFIRMED')


def is_console_identity_request(raw):
    """Despacho explícito por protocolo; nunca ejecuta nada que provenga del cliente."""
    try:
        value = parse_json(raw, limit=65536)
        return isinstance(value, dict) and value.get('protocol') == PROTOCOL
    except Exception:
        return False
