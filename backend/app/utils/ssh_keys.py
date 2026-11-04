"""Validación de claves públicas SSH: única fuente para el portal y el nodo.

Solo biblioteca estándar. Devuelve la clave normalizada (tipo + base64, sin comentario ni
opciones) y su huella SHA256. Nunca acepta ni conserva una clave privada.
"""
import base64
import binascii
import hashlib
import re
import struct

MAX_TEXTO = 800
RSA_MIN_BITS = 3072
LONGITUD_CLAVE = {'ssh-ed25519': 32}
CURVAS = {'ecdsa-sha2-nistp256': b'nistp256', 'ecdsa-sha2-nistp384': b'nistp384', 'ecdsa-sha2-nistp521': b'nistp521'}
TIPOS = frozenset({'ssh-ed25519', 'ssh-rsa', *CURVAS})


class ClaveSshInvalida(ValueError):
    def __init__(self, codigo, mensaje):
        self.codigo, self.mensaje = codigo, mensaje
        super().__init__(codigo)


def _invalida(mensaje='La clave pública SSH no es válida. Pegá una sola línea con el contenido del archivo .pub.'):
    return ClaveSshInvalida('clave_ssh_invalida', mensaje)


def _campos(blob):
    """Parte un blob SSH en sus campos con prefijo de longitud; falla ante cualquier resto o corte."""
    campos, pos = [], 0
    while pos < len(blob):
        if pos + 4 > len(blob):
            raise _invalida()
        (largo,) = struct.unpack('>I', blob[pos:pos + 4])
        pos += 4
        if largo > len(blob) - pos:
            raise _invalida()
        campos.append(blob[pos:pos + largo])
        pos += largo
    return campos


def huella_de(blob):
    return 'SHA256:' + base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip('=')


def validar_clave(texto):
    """Devuelve (tipo, clave_normalizada, huella). Lanza ClaveSshInvalida con un código estable."""
    if not isinstance(texto, str):
        raise _invalida()
    if 'PRIVATE KEY' in texto or 'BEGIN OPENSSH' in texto or 'BEGIN RSA' in texto:
        raise ClaveSshInvalida('clave_ssh_privada',
            'Pegaste una clave privada. Pegá solo la clave pública (el archivo que termina en .pub).')
    limpio = texto.strip()
    if not limpio or len(limpio) > MAX_TEXTO:
        raise _invalida()
    if '\n' in limpio or '\r' in limpio:
        raise _invalida('Pegá una sola clave pública, en una sola línea.')
    if any(ord(c) < 32 or ord(c) == 127 for c in limpio):
        raise _invalida()
    partes = limpio.split()
    if len(partes) < 2:
        raise _invalida()
    tipo, cuerpo = partes[0], partes[1]
    if tipo not in TIPOS:
        raise _invalida('Tipo de clave no admitido. Usá ed25519 (recomendado), ecdsa o RSA de 3072 bits o más.')
    if not re.fullmatch(r'[A-Za-z0-9+/]+={0,2}', cuerpo):
        raise _invalida()
    try:
        blob = base64.b64decode(cuerpo, validate=True)
    except (binascii.Error, ValueError):
        raise _invalida() from None
    campos = _campos(blob)
    if not campos or campos[0] != tipo.encode():
        raise _invalida()
    if tipo == 'ssh-ed25519':
        if len(campos) != 2 or len(campos[1]) != LONGITUD_CLAVE[tipo]:
            raise _invalida()
    elif tipo == 'ssh-rsa':
        if len(campos) != 3:
            raise _invalida()
        modulo = campos[2].lstrip(b'\x00')
        if int.from_bytes(modulo, 'big').bit_length() < RSA_MIN_BITS:
            raise _invalida(f'La clave RSA es demasiado corta (mínimo {RSA_MIN_BITS} bits). Generá una ed25519 con: ssh-keygen -t ed25519')
    else:
        if len(campos) != 3 or campos[1] != CURVAS[tipo] or not campos[2]:
            raise _invalida()
    return tipo, f'{tipo} {cuerpo}', huella_de(blob)
