"""Asignación de identidades de red preautorizadas, bajo el lock de capacidad.

Infraestructura prepara en lote DNS, certificados y reservas DHCP por MAC.
Cada UUID se consume una sola vez, incluso si se retira su antiguo contenedor.
No administra DNS, DHCP o CA ni transmite claves TLS a través de la API.
"""
from copy import deepcopy
import ipaddress
import re
from uuid import UUID
from sqlalchemy import select
from app.config import get_settings
from app.models.identidad_infraestructura import IdentidadInfraestructura
from app.utils.errors import error


def snapshot(profile, instance):
    return {key:deepcopy(instance[key]) for key in ['host','address','mac_address']} | {
        'bridge':profile['bridge'], 'client_cidrs':deepcopy(profile['client_cidrs'])}


async def reservar(db, *, network_id, product, node):
    profiles = get_settings().network_profiles
    try:
        profile = profiles[network_id]
        used = set((await db.scalars(select(IdentidadInfraestructura.resource_uuid))).all())
        candidates = []
        seen = set()
        for name, network in profiles.items():
            for key, item in network.get('instances', {}).items():
                identity = UUID(key)
                if str(identity) != key:
                    raise ValueError()
                for kind, value in [('host',item['host']), ('address',item['address']), ('mac',item['mac_address'].lower())]:
                    if (kind,value) in seen:
                        raise ValueError()
                    seen.add((kind,value))
                address = ipaddress.ip_address(item['address'])
                if (not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?', item['host'])
                    or not re.fullmatch(r'02(?::[0-9a-fA-F]{2}){5}', item['mac_address'])
                    or not any(address in ipaddress.ip_network(cidr) for cidr in network['allowed_cidrs']
                        if ipaddress.ip_network(cidr).version == address.version)):
                    raise ValueError()
                if (name == network_id and node in network['nodes'] and identity not in used
                    and product in item['products']):
                    candidates.append((key, snapshot(profile,item)))
        if candidates:
            key, value = sorted(candidates)[0]
            return UUID(key), {'network_profile_id':network_id, 'resource_uuid':key, 'instance':value}
    except (KeyError,ValueError,TypeError,AttributeError):
        raise error(409, 'red_preparada_invalida', 'Revisá el pool institucional de DNS/TLS/DHCP; no se creó ningún recurso') from None
    raise error(409, 'red_preparada_agotada', 'No quedan destinos de red/TLS preparados para este producto; ampliar el pool institucional')
