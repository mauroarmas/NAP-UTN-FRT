import json
import re
from uuid import uuid4

import pytest

from app.schemas.guest_runner import RunnerError
from infra.runner import console_identity as modulo
from infra.runner.console_identity import ConsoleIdentityExecutor, handle_console_identity_request

CLUSTER = str(uuid4())
ID = 'nap-u12@pve'
PW = 'Xk3_' + 'a1B2c3D4' * 4


class Nodo:
    """Doble de Proxmox: usuarios, ACL, pools, roles y procesos de consola; registra todo comando."""

    def __init__(self, *, pools=('catedra-3', 'catedra-25'), privs='VM.Console,VM.Audit', rol=True):
        self.calls, self.users, self.acl, self.passwords = [], {}, [], {}
        self.pools, self.rol, self.privs = set(pools), rol, privs
        self.procesos = []          # líneas de comando de termproxy en este nodo
        self.fail_on = None

    def __call__(self, argv, *, input=None, timeout=30, accepted_codes=(0,)):
        self.calls.append((list(argv), input))
        if self.fail_on and self.fail_on in argv:
            raise RunnerError('UNCONFIRMED')
        prog, args = argv[0], argv[1:]
        if prog == modulo.PVEUM:
            return self._pveum(args, input)
        if prog == modulo.PVESH:
            assert args[:2] == ['get', '/pools']
            return json.dumps([{'poolid': p} for p in sorted(self.pools)]).encode()
        if prog == modulo.PGREP:
            patron = re.compile(argv[2])
            hits = [p for p in self.procesos if patron.search(p)]
            return ('\n'.join(str(i + 1) for i in range(len(hits))) + '\n').encode() if hits else b''
        if prog == modulo.PKILL:
            patron = re.compile(argv[2])
            self.procesos = [p for p in self.procesos if not patron.search(p)]
            return b''
        raise AssertionError(argv)

    def _pveum(self, args, entrada):
        if args[:2] == ['role', 'list']:
            return json.dumps([{'roleid': 'NapConsola', 'privs': self.privs}] if self.rol else []).encode()
        if args[:2] == ['user', 'list']:
            return json.dumps(list(self.users.values())).encode()
        if args[:2] == ['user', 'add']:
            self.users[args[2]] = {'userid': args[2], 'comment': args[4]}
        elif args[:2] == ['user', 'modify']:
            self.users[args[2]]['comment'] = args[4]
        elif args[:2] == ['user', 'delete']:
            self.users.pop(args[2])
            self.acl = [a for a in self.acl if a['ugid'] != args[2]]
        elif args[0] == 'passwd':
            partes = entrada.decode().split('\n')
            assert partes[0] == partes[1] and len(partes) == 3, 'passwd espera la contraseña dos veces por stdin'
            self.passwords[args[1]] = partes[0]
        elif args[:2] == ['acl', 'list']:
            return json.dumps([{'path': a['path'], 'ugid': a['ugid'], 'roleid': a['roleid'], 'type': 'user'} for a in self.acl]).encode()
        elif args[:2] == ['acl', 'modify']:
            self.acl.append({'path': args[2], 'ugid': args[4], 'roleid': args[6]})
        elif args[:2] == ['acl', 'delete']:
            self.acl = [a for a in self.acl if not (a['path'] == args[2] and a['ugid'] == args[4] and a['roleid'] == args[6])]
        else:
            raise AssertionError(args)
        return b''


def pedido(action='ensure', **cambios):
    valor = {'protocol': 'nap-console-identity/1', 'operation_id': str(uuid4()), 'action': action, 'cluster_uuid': CLUSTER,
        'identidad': ID, 'revision': 1}
    if action == 'ensure':
        valor.update(password_consola=PW, pools=['catedra-3'])
    if action == 'end_sessions':
        valor.update(vmids=[101])
    valor.update(cambios)
    return json.dumps(valor).encode()


def ejecutar(nodo, raw):
    return handle_console_identity_request(raw, executor=ConsoleIdentityExecutor(run_command=nodo, cluster_uuid=CLUSTER, now=lambda: 0))


def test_ensure_crea_la_identidad_fija_la_contrasena_y_concede_solo_el_rol_de_consola():
    nodo = Nodo()
    r = ejecutar(nodo, pedido())
    assert r['status'] == 'succeeded' and r['result'] == {'pools_aplicados': ['catedra-3'], 'pools_pendientes': [],
        'creada': True, 'password': 'aplicada'}
    assert nodo.passwords[ID] == PW
    assert nodo.acl == [{'path': '/pool/catedra-3', 'ugid': ID, 'roleid': 'NapConsola'}]


def test_la_contrasena_nunca_va_en_argv_ni_en_la_respuesta():
    nodo = Nodo()
    r = ejecutar(nodo, pedido())
    assert not any(PW in parte for argv, _ in nodo.calls for parte in argv)
    assert PW not in json.dumps(r)
    assert any(entrada and PW.encode() in entrada for _, entrada in nodo.calls)


def test_ensure_es_idempotente():
    nodo = Nodo()
    ejecutar(nodo, pedido())
    antes = (dict(nodo.users), list(nodo.acl))
    n = len(nodo.calls)
    r = ejecutar(nodo, pedido())
    assert r['result']['password'] == 'sin_cambios' and r['result']['creada'] is False
    assert (nodo.users, nodo.acl) == antes
    escrituras = [a for a, _ in nodo.calls[n:] if a[1:3] in (['user', 'add'], ['acl', 'modify']) or a[1] == 'passwd']
    assert escrituras == []


def test_una_revision_nueva_vuelve_a_fijar_la_contrasena():
    nodo = Nodo()
    ejecutar(nodo, pedido())
    nueva = 'Zz9_' + 'q1W2e3R4' * 4
    r = ejecutar(nodo, pedido(revision=2, password_consola=nueva))
    assert r['result']['password'] == 'aplicada' and nodo.passwords[ID] == nueva


def test_los_pools_inexistentes_quedan_pendientes_y_se_completan_despues():
    nodo = Nodo(pools=('catedra-3',))
    r = ejecutar(nodo, pedido(pools=['catedra-3', 'catedra-7']))
    assert r['result']['pools_aplicados'] == ['catedra-3'] and r['result']['pools_pendientes'] == ['catedra-7']
    nodo.pools.add('catedra-7')
    r = ejecutar(nodo, pedido(pools=['catedra-3', 'catedra-7']))
    assert r['result']['pools_aplicados'] == ['catedra-3', 'catedra-7'] and r['result']['pools_pendientes'] == []


def test_ensure_quita_los_permisos_que_sobran_incluidos_roles_ajenos():
    nodo = Nodo()
    ejecutar(nodo, pedido(pools=['catedra-3', 'catedra-25']))
    nodo.acl.append({'path': '/', 'ugid': ID, 'roleid': 'Administrator'})
    nodo.acl.append({'path': '/pool/catedra-3', 'ugid': ID, 'roleid': 'PVEVMAdmin'})
    ejecutar(nodo, pedido(pools=['catedra-3']))
    assert nodo.acl == [{'path': '/pool/catedra-3', 'ugid': ID, 'roleid': 'NapConsola'}]


def test_no_toca_las_acl_de_otras_identidades():
    nodo = Nodo()
    nodo.acl.append({'path': '/pool/catedra-3', 'ugid': 'nap-u99@pve', 'roleid': 'NapConsola'})
    ejecutar(nodo, pedido())
    assert {'path': '/pool/catedra-3', 'ugid': 'nap-u99@pve', 'roleid': 'NapConsola'} in nodo.acl


def test_retire_con_pools_conserva_la_identidad_y_los_otros_pools():
    nodo = Nodo()
    ejecutar(nodo, pedido(pools=['catedra-3', 'catedra-25']))
    r = ejecutar(nodo, pedido('retire', pools=['catedra-3']))
    assert r['result'] == {'retirada': False, 'pools_quitados': ['catedra-3']}
    assert ID in nodo.users and nodo.acl == [{'path': '/pool/catedra-25', 'ugid': ID, 'roleid': 'NapConsola'}]


def test_retire_sin_pools_elimina_la_identidad_y_sus_permisos():
    nodo = Nodo()
    ejecutar(nodo, pedido(pools=['catedra-3', 'catedra-25']))
    r = ejecutar(nodo, pedido('retire'))
    assert r['result']['retirada'] is True and r['result']['pools_quitados'] == ['catedra-25', 'catedra-3']
    assert ID not in nodo.users and nodo.acl == []
    assert ejecutar(nodo, pedido('retire'))['result'] == {'retirada': True, 'pools_quitados': []}


def test_end_sessions_termina_solo_las_consolas_de_esos_contenedores_en_este_nodo():
    nodo = Nodo()
    nodo.procesos = ['/usr/bin/termproxy 5900 --path /vms/101 --perm VM.Console -- /usr/bin/ssh x',
                     '/usr/bin/termproxy 5901 --path /vms/1010 --perm VM.Console -- /usr/bin/ssh x',
                     '/usr/bin/termproxy 5902 --path /vms/102 --perm VM.Console -- /usr/bin/ssh x']
    r = ejecutar(nodo, pedido('end_sessions', vmids=[101]))
    assert r['result'] == {'terminadas': 1}
    assert len(nodo.procesos) == 2 and not any('/vms/101 ' in p for p in nodo.procesos)
    assert ejecutar(nodo, pedido('end_sessions', vmids=[101]))['result'] == {'terminadas': 0}


def test_probe_informa_existencia_y_pools_sin_secretos():
    nodo = Nodo()
    assert ejecutar(nodo, pedido('probe'))['result'] == {'existe': False, 'pools': [], 'roles': []}
    ejecutar(nodo, pedido(pools=['catedra-25']))
    r = ejecutar(nodo, pedido('probe'))
    assert r['result'] == {'existe': True, 'pools': ['catedra-25'], 'roles': ['NapConsola']}
    assert PW not in json.dumps(r)


def test_un_clúster_distinto_es_un_fallo_definitivo_sin_efecto():
    nodo = Nodo()
    r = handle_console_identity_request(pedido(cluster_uuid=str(uuid4())),
        executor=ConsoleIdentityExecutor(run_command=nodo, cluster_uuid=CLUSTER, now=lambda: 0))
    assert r['status'] == 'failed' and r['error']['code'] == 'IDENTITY_MISMATCH' and r['identity_verified'] is False
    assert not nodo.users


@pytest.mark.parametrize('kwargs', [{'rol': False}, {'privs': 'VM.Console,VM.Audit,VM.PowerMgmt'}, {'privs': 'VM.Console'}])
def test_si_el_rol_de_consola_no_es_exactamente_el_esperado_no_se_hace_nada(kwargs):
    nodo = Nodo(**kwargs)
    r = ejecutar(nodo, pedido())
    assert r['status'] == 'failed' and r['error']['code'] == 'ROLE_UNAVAILABLE'
    assert not nodo.users and not nodo.acl


def test_un_fallo_al_fijar_la_contrasena_queda_sin_confirmar_y_no_filtra_nada():
    nodo = Nodo()
    nodo.fail_on = 'passwd'
    r = ejecutar(nodo, pedido())
    assert r['status'] == 'unconfirmed' and PW not in json.dumps(r) and PW not in repr(r)


def test_entradas_invalidas_se_rechazan_sin_ejecutar_nada():
    nodo = Nodo()
    for raw in (pedido(identidad='root@pam'), pedido(pools=['/']), b'no es json', pedido(extra=1)):
        r = handle_console_identity_request(raw, executor=ConsoleIdentityExecutor(run_command=nodo, cluster_uuid=CLUSTER, now=lambda: 0))
        assert r['status'] == 'failed' and r['error']['code'] == 'INVALID_REQUEST'
    assert nodo.calls == []
