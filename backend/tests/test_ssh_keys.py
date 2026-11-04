import base64
import shutil
import subprocess

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa

from app.utils.ssh_keys import ClaveSshInvalida, validar_clave


def _publica(clave):
    return clave.public_key().public_bytes(serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH).decode()


@pytest.fixture(scope='module')
def claves():
    return {
        'ed25519': _publica(ed25519.Ed25519PrivateKey.generate()),
        'ecdsa256': _publica(ec.generate_private_key(ec.SECP256R1())),
        'ecdsa384': _publica(ec.generate_private_key(ec.SECP384R1())),
        'rsa3072': _publica(rsa.generate_private_key(65537, 3072)),
        'rsa2048': _publica(rsa.generate_private_key(65537, 2048)),
    }


@pytest.mark.parametrize('nombre,tipo', [('ed25519', 'ssh-ed25519'), ('ecdsa256', 'ecdsa-sha2-nistp256'),
    ('ecdsa384', 'ecdsa-sha2-nistp384'), ('rsa3072', 'ssh-rsa')])
def test_admite_los_tipos_aceptados(claves, nombre, tipo):
    resultado = validar_clave(claves[nombre])
    assert resultado[0] == tipo
    assert resultado[1] == ' '.join(claves[nombre].split()[:2])
    assert resultado[2].startswith('SHA256:') and '=' not in resultado[2]


def test_descarta_el_comentario(claves):
    assert validar_clave(claves['ed25519'] + ' docente@laptop con espacios')[1] == ' '.join(claves['ed25519'].split()[:2])


def test_tolera_espacios_alrededor(claves):
    assert validar_clave('  ' + claves['ed25519'] + '\n')[0] == 'ssh-ed25519'


def test_huella_coincide_con_ssh_keygen(claves, tmp_path):
    if not shutil.which('ssh-keygen'):
        pytest.skip('ssh-keygen no disponible')
    archivo = tmp_path / 'k.pub'
    archivo.write_text(claves['ed25519'] + '\n')
    esperado = subprocess.run(['ssh-keygen', '-lf', str(archivo)], capture_output=True, text=True, check=True).stdout.split()[1]
    assert validar_clave(claves['ed25519'])[2] == esperado


def test_rechaza_rsa_corta(claves):
    with pytest.raises(ClaveSshInvalida) as exc:
        validar_clave(claves['rsa2048'])
    assert exc.value.codigo == 'clave_ssh_invalida' and '3072' in exc.value.mensaje


@pytest.mark.parametrize('texto', [
    '-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjE=\n-----END OPENSSH PRIVATE KEY-----',
    '-----BEGIN RSA PRIVATE KEY-----\nabc\n-----END RSA PRIVATE KEY-----',
])
def test_rechaza_clave_privada(texto):
    with pytest.raises(ClaveSshInvalida) as exc:
        validar_clave(texto)
    assert exc.value.codigo == 'clave_ssh_privada'


def test_rechaza_varias_lineas(claves):
    with pytest.raises(ClaveSshInvalida):
        validar_clave(claves['ed25519'] + '\n' + claves['ecdsa256'])


def test_rechaza_opciones_por_delante(claves):
    with pytest.raises(ClaveSshInvalida):
        validar_clave('command="rm -rf /",no-pty ' + claves['ed25519'])


@pytest.mark.parametrize('texto', ['', '   ', 'ssh-ed25519', 'ssh-ed25519 !!!', 'ssh-dss AAAA', None, 5, 'x' * 801])
def test_rechaza_basura(texto):
    with pytest.raises(ClaveSshInvalida):
        validar_clave(texto)


def test_rechaza_tipo_interno_distinto(claves):
    tipo, cuerpo = claves['ed25519'].split()[:2]
    with pytest.raises(ClaveSshInvalida):
        validar_clave('ssh-rsa ' + cuerpo)


def test_rechaza_blob_truncado_o_con_resto(claves):
    cuerpo = claves['ed25519'].split()[1]
    crudo = base64.b64decode(cuerpo)
    for variante in (crudo[:-3], crudo + b'\x00'):
        with pytest.raises(ClaveSshInvalida):
            validar_clave('ssh-ed25519 ' + base64.b64encode(variante).decode())


def test_rechaza_caracteres_de_control(claves):
    with pytest.raises(ClaveSshInvalida):
        validar_clave(claves['ed25519'] + ' co\x07mentario')
