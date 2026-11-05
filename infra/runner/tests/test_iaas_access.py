import hashlib
import json
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from app.schemas.guest_runner import RunnerError
from infra.runner import iaas_access as modulo
from infra.runner.iaas_access import (AUTHORIZED, SSHD_CONTENIDO, SSHD_DROPIN, SUDOERS, SUDOERS_CONTENIDO,
    IaasAccessExecutor, handle_iaas_access_request)

RESOURCE, NONCE, VMID = str(uuid4()), 'n' * 30, 101


def nueva_clave():
    publica = ed25519.Ed25519PrivateKey.generate().public_key()
    return publica.public_bytes(serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH).decode()


class Nodo:
    """Doble del nodo Proxmox y del invitado: registra todo comando y simula archivos y usuarios."""

    def __init__(self, *, pool='catedra-3', running=True, sshd=True, sudo=True, marker=None):
        self.calls, self.files, self.user, self.running = [], {}, False, running
        self.installed = {p for p, ok in (('/usr/sbin/sshd', sshd), ('/usr/bin/sudo', sudo)) if ok}
        self.pool = pool
        self.marker = marker or {'resource_uuid': RESOURCE, 'pool': 'catedra-3', 'nonce_sha256': hashlib.sha256(NONCE.encode()).hexdigest()}
        self.fail_on = None
        self.shadow = {'nap': '*', 'root': '$6$sal$hashviejo'}   # lo que hay en /etc/shadow del invitado
        self.salida_ip = b'2: eth0    inet 192.168.100.18/24 metric 1024 brd 192.168.100.255 scope global dynamic eth0\n       valid_lft 3000sec\n'

    def __call__(self, argv, *, input=None, timeout=30, accepted_codes=(0,)):
        self.calls.append((list(argv), input))
        if self.fail_on and self.fail_on in argv:
            raise RunnerError('UNCONFIRMED')
        if argv[0] == '/usr/bin/pvesh' and argv[2] == '/cluster/resources':
            return json.dumps([{'vmid': VMID, 'node': 'pve91', 'type': 'lxc', 'pool': self.pool}]).encode()
        if argv[0] == '/usr/bin/pvesh':
            return json.dumps({'description': json.dumps({'nap': self.marker}), 'unprivileged': 1}).encode()
        if argv[:2] == [modulo.PCT, 'status']:
            return b'status: running\n' if self.running else b'status: stopped\n'
        assert argv[:2] == [modulo.PCT, 'exec'] and argv[3] == '--', argv
        inner = argv[4:]
        if inner[:2] == ['/bin/sh', '-c'] and inner[2] == modulo.DIRECCION:
            return self.salida_ip
        if inner[:2] == ['/bin/sh', '-c'] and inner[3] == 'nap-test':
            return b'si\n' if inner[4] in self.installed else b''
        if inner[:2] == ['/bin/sh', '-c'] and inner[3] == 'nap-comparar':
            return b'si\n' if self.shadow.get(inner[4]) == '$6$sal$' + input.rstrip(b'\0').decode() else b'no\n'
        if inner[:2] == ['/bin/sh', '-c']:
            self.files[inner[4]] = input.decode()
            return b''
        if inner[0] == '/usr/bin/getent' and inner[1] == 'shadow':
            h = self.shadow.get(inner[2])
            return (inner[2] + ':' + h + ':20000:0:99999:7:::\n').encode() if h is not None else b''
        if inner[0] == '/usr/sbin/chpasswd':
            usuario, clave = input.decode().rstrip('\n').split(':', 1)
            self.shadow[usuario] = '$6$sal$' + clave
            return b''
        if inner[0] == '/usr/sbin/usermod' and inner[1] == '-p':
            self.shadow[inner[3]] = inner[2]
            return b''
        if inner[0] == '/usr/bin/getent':
            return b'nap:*:1000:1000::/home/nap:/bin/bash\n' if self.user else b''
        if inner[0] == '/usr/sbin/useradd':
            self.user = True
            return b''
        if inner[0] == '/bin/cat':
            return self.files.get(inner[1], '').encode()
        if inner[0] == '/usr/sbin/sshd' and inner[1] == '-T':
            if SSHD_DROPIN in self.files:
                return b'passwordauthentication no\npermitrootlogin no\npubkeyauthentication yes\nallowusers nap\n'
            return b'passwordauthentication yes\npermitrootlogin yes\n'
        if inner[0] == '/bin/bash':
            return b'SSH-2.0-OpenSSH_9.6' if SSHD_DROPIN in self.files else b''
        return b''


def pedido(accion='configure', clave=None, huella=None, password=None):
    valor = {'protocol': 'nap-iaas-access/1', 'operation_id': str(uuid4()), 'action': accion, 'cluster_uuid': str(uuid4()),
        'resource_uuid': RESOURCE, 'node': 'pve91', 'vmid': VMID, 'pool': 'catedra-3', 'nonce': NONCE, 'revision': 2, 'usuario': 'nap'}
    if accion == 'configure':
        valor['clave_publica'] = clave
        if password is not None:
            valor['password_consola'] = password
    else:
        valor['huella'] = huella
    return json.dumps(valor).encode()


def ejecutor(nodo):
    return IaasAccessExecutor(run_command=nodo, local_node='pve91', sleep=lambda _: None)


def test_configure_instala_usuario_clave_y_endurece_sshd():
    nodo, clave = Nodo(), nueva_clave()
    respuesta = handle_iaas_access_request(pedido(clave=clave), executor=ejecutor(nodo))
    assert respuesta['status'] == 'succeeded' and respuesta['identity_verified'] is True
    assert respuesta['result']['ready'] is True and respuesta['result']['usuario'] == 'nap'
    assert nodo.files[AUTHORIZED] == ' '.join(clave.split()[:2]) + '\n'
    assert nodo.files[SUDOERS] == SUDOERS_CONTENIDO and nodo.files[SSHD_DROPIN] == SSHD_CONTENIDO
    assert 'PasswordAuthentication no' in SSHD_CONTENIDO and 'PermitRootLogin no' in SSHD_CONTENIDO


def test_la_clave_nunca_aparece_en_argv():
    nodo, clave = Nodo(), nueva_clave()
    handle_iaas_access_request(pedido(clave=clave), executor=ejecutor(nodo))
    cuerpo = clave.split()[1]
    assert not any(cuerpo in parte for argv, _ in nodo.calls for parte in argv)
    assert any(entrada and cuerpo.encode() in entrada for _, entrada in nodo.calls)  # sí viaja por stdin


def test_configure_es_convergente_al_repetirlo():
    nodo, clave = Nodo(), nueva_clave()
    primera = handle_iaas_access_request(pedido(clave=clave), executor=ejecutor(nodo))
    archivos = dict(nodo.files)
    segunda = handle_iaas_access_request(pedido(clave=clave), executor=ejecutor(nodo))
    assert primera['status'] == segunda['status'] == 'succeeded' and nodo.files == archivos
    assert sum(1 for argv, _ in nodo.calls if argv[4:5] == ['/usr/sbin/useradd']) == 1


def test_reemplazar_deja_solo_la_clave_nueva():
    nodo, vieja, nueva = Nodo(), nueva_clave(), nueva_clave()
    handle_iaas_access_request(pedido(clave=vieja), executor=ejecutor(nodo))
    handle_iaas_access_request(pedido(clave=nueva), executor=ejecutor(nodo))
    assert nodo.files[AUTHORIZED] == ' '.join(nueva.split()[:2]) + '\n' and vieja.split()[1] not in nodo.files[AUTHORIZED]


@pytest.mark.parametrize('nodo', [Nodo(pool='catedra-9'), Nodo(marker={'resource_uuid': str(uuid4()), 'pool': 'catedra-3', 'nonce_sha256': 'x'})])
def test_vmid_reutilizado_no_recibe_la_clave(nodo):
    respuesta = handle_iaas_access_request(pedido(clave=nueva_clave()), executor=ejecutor(nodo))
    assert respuesta['status'] == 'failed' and respuesta['error']['code'] == 'IDENTITY_MISMATCH'
    assert respuesta['identity_verified'] is False and nodo.files == {}
    assert not any(argv[:2] == [modulo.PCT, 'exec'] for argv, _ in nodo.calls)


def test_nodo_distinto_falla_cerrado():
    nodo = Nodo()
    respuesta = handle_iaas_access_request(pedido(clave=nueva_clave()),
        executor=IaasAccessExecutor(run_command=nodo, local_node='frt'))
    assert respuesta['error']['code'] == 'IDENTITY_MISMATCH' and nodo.files == {}


@pytest.mark.parametrize('nodo,codigo', [(Nodo(running=False), 'GUEST_NOT_RUNNING'), (Nodo(sshd=False), 'SSHD_UNAVAILABLE'),
    (Nodo(sudo=False), 'SUDO_UNAVAILABLE')])
def test_precondiciones_fallan_sin_efecto(nodo, codigo):
    respuesta = handle_iaas_access_request(pedido(clave=nueva_clave()), executor=ejecutor(nodo))
    assert respuesta['status'] == 'failed' and respuesta['error']['code'] == codigo
    assert nodo.files == {} and nodo.user is False


def test_un_corte_a_mitad_queda_sin_confirmar():
    nodo = Nodo()
    nodo.fail_on = 'restart'
    respuesta = handle_iaas_access_request(pedido(clave=nueva_clave()), executor=ejecutor(nodo))
    assert respuesta['status'] == 'unconfirmed' and respuesta['error']['retryable'] is True


def test_probe_confirma_y_detecta_huella_distinta():
    nodo, clave = Nodo(), nueva_clave()
    huella = handle_iaas_access_request(pedido(clave=clave), executor=ejecutor(nodo))['result']['huella']
    assert handle_iaas_access_request(pedido('probe', huella=huella), executor=ejecutor(nodo))['status'] == 'succeeded'
    otra = handle_iaas_access_request(pedido(clave=nueva_clave()), executor=ejecutor(Nodo()))['result']['huella']
    malo = handle_iaas_access_request(pedido('probe', huella=otra), executor=ejecutor(nodo))
    assert malo['error']['code'] == 'PROBE_FAILED'


def test_probe_falla_si_sshd_acepta_contrasena():
    nodo, clave = Nodo(), nueva_clave()
    huella = handle_iaas_access_request(pedido(clave=clave), executor=ejecutor(nodo))['result']['huella']
    del nodo.files[SSHD_DROPIN]
    assert handle_iaas_access_request(pedido('probe', huella=huella), executor=ejecutor(nodo))['error']['code'] == 'PROBE_FAILED'


def test_solicitud_invalida_se_rechaza_sin_tocar_el_nodo():
    nodo = Nodo()
    respuesta = handle_iaas_access_request(b'{"protocol":"nap-iaas-access/1"}', executor=ejecutor(nodo))
    assert respuesta['status'] == 'failed' and respuesta['error']['code'] == 'INVALID_REQUEST' and nodo.calls == []


def test_despacho_por_protocolo():
    from infra.runner.nap_guest_runner import is_iaas_access_request
    assert is_iaas_access_request(pedido(clave=nueva_clave()))
    assert not is_iaas_access_request(b'{"protocol":"nap-guest-runner/1"}')
    assert not is_iaas_access_request(b'no json')


def test_informa_la_ip_real_del_contenedor():
    nodo, clave = Nodo(), nueva_clave()
    respuesta = handle_iaas_access_request(pedido(clave=clave), executor=ejecutor(nodo))
    assert respuesta['result']['direccion'] == '192.168.100.18'
    huella = respuesta['result']['huella']
    probe = handle_iaas_access_request(pedido('probe', huella=huella), executor=ejecutor(nodo))
    assert probe['result']['direccion'] == '192.168.100.18'


@pytest.mark.parametrize('salida', [b'', b'2: eth0 inet6 fe80::1/64 scope link\n', b'2: eth0 inet no-es-ip/24 scope global\n', b'inet\n'])
def test_sin_una_ipv4_valida_no_inventa_direccion(salida):
    nodo, clave = Nodo(), nueva_clave()
    nodo.salida_ip = salida
    respuesta = handle_iaas_access_request(pedido(clave=clave), executor=ejecutor(nodo))
    assert respuesta['status'] == 'succeeded' and 'direccion' not in respuesta['result']


# --- Contraseña de consola para `nap` y `root` sin contraseña (feature 021) -------------------------------------

PASSWORD = 'Xk3_' + 'a1B2c3D4' * 4          # 36 caracteres válidos


def _configurar(nodo, password=PASSWORD, clave=None):
    return handle_iaas_access_request(pedido(clave=clave or nueva_clave(), password=password), executor=ejecutor(nodo))


def test_configure_con_password_fija_la_contrasena_de_nap_y_bloquea_root():
    nodo = Nodo()
    respuesta = _configurar(nodo)
    assert respuesta['status'] == 'succeeded' and respuesta['result']['consola'] == 'aplicada'
    assert nodo.shadow['nap'] == '$6$sal$' + PASSWORD
    assert nodo.shadow['root'] == '*'


def test_la_contrasena_viaja_solo_por_stdin_y_nunca_aparece_en_argv():
    nodo = Nodo()
    _configurar(nodo)
    assert not any(PASSWORD in parte for argv, _ in nodo.calls for parte in argv)
    assert any(entrada and PASSWORD.encode() in entrada for _, entrada in nodo.calls)


def test_repetir_con_la_misma_contrasena_no_cambia_nada():
    nodo = Nodo()
    _configurar(nodo)
    antes = dict(nodo.shadow)
    chpasswd = sum(1 for argv, _ in nodo.calls if argv[4:5] == ['/usr/sbin/chpasswd'])
    segunda = _configurar(nodo)
    assert segunda['status'] == 'succeeded' and segunda['result']['consola'] == 'sin_cambios'
    assert nodo.shadow == antes
    assert sum(1 for argv, _ in nodo.calls if argv[4:5] == ['/usr/sbin/chpasswd']) == chpasswd


def test_no_pisa_la_contrasena_que_la_persona_cambio():
    nodo = Nodo()
    _configurar(nodo)
    nodo.shadow['nap'] = '$6$sal$otra-que-puso-la-persona'
    respuesta = _configurar(nodo)
    assert respuesta['result']['consola'] == 'conservada'
    assert nodo.shadow['nap'] == '$6$sal$otra-que-puso-la-persona'


def test_root_con_contrasena_se_bloquea_aunque_nap_ya_la_tenga():
    nodo = Nodo()
    _configurar(nodo)
    nodo.shadow['root'] = '$6$sal$volvio'
    assert _configurar(nodo)['status'] == 'succeeded'
    assert nodo.shadow['root'] == '*'


def test_sin_password_el_comportamiento_de_la_017_no_cambia():
    nodo = Nodo()
    nodo.shadow['root'] = '$6$sal$conserva'
    respuesta = handle_iaas_access_request(pedido(clave=nueva_clave()), executor=ejecutor(nodo))
    assert respuesta['status'] == 'succeeded' and 'consola' not in respuesta['result']
    assert nodo.shadow['nap'] == '*' and nodo.shadow['root'] == '$6$sal$conserva'


def test_un_fallo_al_fijar_la_contrasena_queda_sin_confirmar_y_no_filtra_nada():
    nodo = Nodo()
    nodo.fail_on = '/usr/sbin/chpasswd'
    respuesta = _configurar(nodo)
    assert respuesta['status'] == 'unconfirmed'
    assert PASSWORD not in json.dumps(respuesta) and PASSWORD not in repr(respuesta)
    assert nodo.shadow['nap'] == '*'


def test_la_respuesta_nunca_lleva_la_contrasena_ni_su_hash():
    nodo = Nodo()
    texto = json.dumps(_configurar(nodo))
    assert PASSWORD not in texto and '$6$' not in texto


def test_probe_no_toca_contrasenas():
    nodo, clave = Nodo(), nueva_clave()
    _configurar(nodo, clave=clave)
    antes = dict(nodo.shadow)
    huella = modulo.validar_clave(clave)[2]
    respuesta = handle_iaas_access_request(pedido('probe', huella=huella), executor=ejecutor(nodo))
    assert respuesta['status'] == 'succeeded' and nodo.shadow == antes
