"""Destino de la consola nativa: resuelve un nodo alcanzable sin depender de uno solo."""
import asyncio
import re

from app.utils.errors import error

SONDEO_SEGUNDOS = 2.0
_HOST = re.compile(r'^(?=.{1,253}$)([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)(\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$')
_IPV4 = re.compile(r'^\d{1,3}(\.\d{1,3}){3}$')


def validar_nodos(nodos):
    """Comprueba la clave `nodos` del perfil; lanza ValueError si no es utilizable."""
    if not isinstance(nodos, dict) or not nodos:
        raise ValueError('nodos')
    for name, entry in nodos.items():
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9._-]{1,64}', name):
            raise ValueError('nodos')
        if not isinstance(entry, dict) or set(entry) - {'host', 'port', 'portal_host'} or 'host' not in entry:
            raise ValueError('nodos')
        host, port = entry['host'], entry.get('port', 8006)
        for direccion in (host, entry.get('portal_host', host)):
            if not isinstance(direccion, str) or not _HOST.fullmatch(direccion):
                raise ValueError('nodos')
            if _IPV4.fullmatch(direccion) and any(int(part) > 255 for part in direccion.split('.')):
                raise ValueError('nodos')
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError('nodos')
    return nodos


async def _responde(host, port):
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), SONDEO_SEGUNDOS)
    except (OSError, asyncio.TimeoutError):
        return False
    writer.close()
    try:
        await writer.wait_closed()
    except OSError:
        pass
    return True


async def resolver_destino(profile, nodo_contenedor, *, sondeo=None):
    """Devuelve (host, puerto): el nodo del contenedor y, si no responde, otro del clúster.

    El nodo que aloja el contenedor debe figurar en el perfil; si no, la consola no está habilitada
    para ese servicio. Si ningún nodo responde, falla sin devolver un destino equivocado.
    """
    sondeo = sondeo or _responde
    try:
        nodos = validar_nodos(profile.get('nodos'))
        if nodo_contenedor not in nodos:
            raise ValueError('nodo')
    except (ValueError, AttributeError):
        raise error(409, 'consola_no_habilitada',
            'La consola todavía no está habilitada para este servicio. Pedíselo a administración.') from None
    order = [nodo_contenedor] + sorted(name for name in nodos if name != nodo_contenedor)
    for name in order:
        entry = nodos[name]
        port = entry.get('port', 8006)
        if await sondeo(entry['host'], port):
            return entry['host'], port
    raise error(503, 'consola_nodo_no_disponible',
        'La consola no está disponible ahora. Probá de nuevo en unos minutos.', reintentable=True)
