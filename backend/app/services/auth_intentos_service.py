"""Límites móviles persistidos y compartidos entre procesos de API."""
from datetime import datetime, timedelta
import hashlib
import hmac
from ipaddress import ip_address, ip_network
import math

from sqlalchemy import select, text

from app.config import get_settings
from app.models.autenticacion import IntentoAutenticacion
from app.utils.clock import clock, db_utc
from app.utils.errors import error

WINDOW = timedelta(minutes=15)


def origen_remoto(request):
    remote = request.client.host if request.client else 'unknown'
    trusted = [ip_network(value) for value in get_settings().trusted_proxy_networks]
    try:
        if any(ip_address(remote) in network for network in trusted):
            chain = [ip_address(value.strip()) for value in request.headers.get('x-forwarded-for', '').split(',') if value.strip()]
            for address in reversed(chain):
                if not any(address in network for network in trusted):
                    return str(address)
    except ValueError:
        pass
    return remote


def cuenta_identificador(user, supplied=''):
    return f'user:{user.id}' if user else 'unknown:' + supplied.strip().casefold()


def _key(kind, value):
    secret = get_settings().csrf_secret
    if not secret:
        raise error(503, 'configuracion_autenticacion', 'Configurar autenticación en el servidor')
    return hmac.new(secret.encode(), f'nap:attempt:{kind}:{value}'.encode(), hashlib.sha256).hexdigest()


async def _entries(db, account, origin):
    values = [('cuenta', _key('cuenta', account)), ('origen', _key('origen', origin))]
    entries = []
    for kind, key in values:
        if db.bind.dialect.name == 'postgresql':
            lock = int.from_bytes(hashlib.sha256(f'auth-attempt:{kind}:{key}'.encode()).digest()[:8], 'big', signed=True)
            await db.execute(text('SELECT pg_advisory_xact_lock(:lock)'), {'lock': lock})
        entry = await db.scalar(select(IntentoAutenticacion).where(IntentoAutenticacion.clase == kind,
            IntentoAutenticacion.clave == key).with_for_update().execution_options(populate_existing=True))
        if entry is None:
            entry = IntentoAutenticacion(clase=kind, clave=key, fallos_recientes=[], updated_at=clock.now())
            db.add(entry)
            await db.flush()
        entries.append(entry)
    return entries


def _prune(entry):
    cutoff = clock.now() - WINDOW
    entry.fallos_recientes = [instant for instant in entry.fallos_recientes if datetime.fromisoformat(instant) > cutoff]
    entry.updated_at = clock.now()


async def comprobar_limite(db, account, origin):
    entries = await _entries(db, account, origin)
    for entry in entries:
        _prune(entry)
        if entry.bloqueado_hasta and db_utc(entry.bloqueado_hasta) > clock.now():
            seconds = max(1, math.ceil((db_utc(entry.bloqueado_hasta) - clock.now()).total_seconds()))
            raise error(429, 'espera_autenticacion', 'Esperá antes de volver a intentar',
                        headers={'Retry-After': str(seconds)}, reintentar_en_segundos=seconds, reintentable=True)


async def registrar_fallo(db, account, origin):
    for entry in await _entries(db, account, origin):
        _prune(entry)
        entry.fallos_recientes = [*entry.fallos_recientes, clock.now().isoformat()]
        limit = 5 if entry.clase == 'cuenta' else 30
        if len(entry.fallos_recientes) >= limit:
            entry.bloqueado_hasta = clock.now() + WINDOW
        # No se acumula una historia de identificadores o direcciones.
        entry.fallos_recientes = entry.fallos_recientes[-limit:]
