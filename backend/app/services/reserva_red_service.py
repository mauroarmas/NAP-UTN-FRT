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
    value = {key:deepcopy(instance[key]) for key in ['host','address','mac_address']} | {
        'bridge':profile['bridge'], 'client_cidrs':deepcopy(profile['client_cidrs'])}
    if profile.get('ip_mode','dhcp') == 'static':
        address=ipaddress.ip_address(instance['address'])
        network=ipaddress.ip_network(profile['static_cidr'])
        gateway=ipaddress.ip_address(profile['gateway'])
        if (network.version!=4 or address not in network or gateway not in network
            or address in {network.network_address,network.broadcast_address,gateway}
            or gateway in {network.network_address,network.broadcast_address}
            or not any(network.subnet_of(ipaddress.ip_network(cidr)) for cidr in profile['allowed_cidrs']
                       if ipaddress.ip_network(cidr).version==4)):
            raise ValueError('Red estática fuera del alcance autorizado')
        value['static_ip']={'cidr':f'{address}/{network.prefixlen}','gateway':str(gateway)}
    elif profile.get('ip_mode','dhcp') != 'dhcp':
        raise ValueError('Modo de red no admitido')
    return value


def aplicar_asignacion(net0, instance):
    """Sólo una asignación persistida puede agregar MAC/IP; nunca datos del formulario."""
    mac=instance['mac_address']
    if not re.fullmatch(r'02(?::[0-9a-fA-F]{2}){5}',mac):raise ValueError('MAC no autorizada')
    if 'static_ip' in instance:
        value=instance['static_ip'];address=ipaddress.ip_interface(value['cidr'])
        gateway=ipaddress.ip_address(value['gateway'])
        if address.version!=4 or str(address.ip)!=instance['address'] or gateway not in address.network:
            raise ValueError('Dirección estática incoherente')
        if ',ip=dhcp' not in net0:raise ValueError('Configuración base no validada')
        net0=net0.replace(',ip=dhcp',f',ip={address},gw={gateway}',1)
    return net0+',hwaddr='+mac


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
