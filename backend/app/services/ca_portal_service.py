"""Confianza del portal en la CA pública de los nodos (APPLICATION_GATEWAY_CA_FILE).

Sin esa CA el portal no puede verificar el TLS de las aplicaciones. Python usaría en silencio las CA del
sistema, la verificación fallaría con un error genérico y el pedido quedaría reintentando. Aquí se
diagnostica de forma explícita. Sólo se evalúa el certificado público; la clave de la CA nunca va al portal.
"""
import ssl
from pathlib import Path

from app.config import get_settings
from app.services.infraestructura_io import InfraNoVerificable
from app.utils.errors import error

MENSAJES = {
    'ca_portal_no_configurada': ('El portal no tiene configurada la CA pública de los nodos (APPLICATION_GATEWAY_CA_FILE). '
        'Sin ella no puede verificar el acceso TLS de las aplicaciones. Configurá el certificado público (nunca la clave privada).'),
    'ca_portal_ilegible': ('El portal no puede leer el archivo de la CA pública de los nodos. '
        'Revisá que exista, sea un archivo regular y esté montado en el servicio.'),
    'ca_portal_invalida': ('El archivo de la CA pública de los nodos no contiene certificados válidos. '
        'Debe ser el certificado público (PEM) de la CA que firma las instancias.'),
}


class CaPortalNoDisponible(InfraNoVerificable):
    """Causa conocida de una verificación pendiente; el código y el detalle son textos fijos."""
    def __init__(self, codigo):
        super().__init__(incierto=True)
        self.codigo_seguro = codigo
        self.detalle_seguro = MENSAJES[codigo]


def estado_ca_portal(ruta=None):
    """None si el portal puede confiar en la CA configurada; si no, el código del problema."""
    ruta = get_settings().application_gateway_ca_file if ruta is None else ruta
    if not ruta:
        return 'ca_portal_no_configurada'
    try:
        archivo = Path(ruta)
        if not archivo.is_file() or archivo.stat().st_size > 1048576:
            return 'ca_portal_ilegible'
        texto = archivo.read_text(encoding='utf-8')
    except (OSError, UnicodeError):
        return 'ca_portal_ilegible'
    if '-----BEGIN CERTIFICATE-----' not in texto:
        return 'ca_portal_invalida'
    try:
        ssl.create_default_context(cadata=texto)
    except (ssl.SSLError, ValueError):
        return 'ca_portal_invalida'
    return None


def exigir_ca_portal(ruta=None):
    problema = estado_ca_portal(ruta)
    if problema:
        raise error(409, problema, MENSAJES[problema])
