"""Asignación de redes institucionales, bajo el lock compartido de capacidad.

Infraestructura prepara en lote DNS, certificados y reservas DHCP por MAC.
La rama histórica consume cada UUID una sola vez. La 011 reutiliza slots sólo
tras ausencia confirmada, conservando filas históricas e identidades distintas.
No administra DNS, DHCP o CA ni transmite claves TLS a través de la API.
"""
from copy import deepcopy
from hashlib import sha256
import ipaddress
import json
import re
from uuid import UUID
from sqlalchemy import select
from app.config import get_settings
from app.models.identidad_infraestructura import IdentidadInfraestructura
from app.utils.errors import error


# La rama 011 no transforma los UUID preasignados de la red histórica.
def _network_error():
    return error(409, 'red_aplicacion_invalida', 'La red de aplicaciones requiere revisión de infraestructura')


def _network_hash(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def validar_red_aplicacion(network_id, *, cluster_uuid, node, settings=None):
    """Sólo consulta perfiles institucionales; no resuelve DNS ni cambia el nodo."""
    settings = settings or get_settings()
    try:
        profiles = settings.application_network_profiles
        if type(profiles) is not dict or not 1 <= len(profiles) <= 50 or network_id not in profiles: raise ValueError()
        seen, management = set(), set()
        try: management.add(str(ipaddress.ip_address(settings.proxmox_host)))
        except ValueError: pass  # Los hosts por DNS requieren sus IP declaradas abajo.
        for name, profile in profiles.items():
            if (not re.fullmatch(r'[a-z][a-z0-9-]{0,63}', name) or type(profile) is not dict
                    or set(profile) != {'schema_version', 'revision', 'cluster_uuid', 'nodes', 'bridge',
                        'allowed_cidrs', 'client_cidrs', 'static_cidr', 'gateway', 'management_addresses', 'slots'}
                    or profile['schema_version'] != 'nap-application-network/1'
                    or type(profile['revision']) is not int or not 1 <= profile['revision'] <= 2**31-1
                    or str(UUID(profile['cluster_uuid'])) != profile['cluster_uuid']): raise ValueError()
            for key in ('nodes', 'allowed_cidrs', 'client_cidrs', 'management_addresses'):
                if type(profile[key]) is not list or not 1 <= len(profile[key]) <= 100: raise ValueError()
                if any(type(v) is not str for v in profile[key]) or len(set(profile[key])) != len(profile[key]): raise ValueError()
            if any(not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,99}', n) for n in profile['nodes']): raise ValueError()
            if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,14}', profile['bridge']): raise ValueError()
            cidr = ipaddress.ip_network(profile['static_cidr'], strict=True)
            gateway = ipaddress.ip_address(profile['gateway'])
            allowed = [ipaddress.ip_network(v, strict=True) for v in profile['allowed_cidrs']]
            clients = [ipaddress.ip_network(v, strict=True) for v in profile['client_cidrs']]
            if (cidr.version != 4 or gateway not in cidr or gateway in {cidr.network_address, cidr.broadcast_address}
                    or not any(cidr.subnet_of(v) for v in allowed if v.version == 4)
                    or any(v.prefixlen == 0 for v in allowed + clients)): raise ValueError()
            management.update(str(ipaddress.ip_address(v)) for v in profile['management_addresses'])
            management.add(str(gateway))
            slots = profile['slots']
            if type(slots) is not dict or not 1 <= len(slots) <= 256: raise ValueError()
            for slot_id, item in slots.items():
                if (not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', slot_id) or type(item) is not dict
                        or set(item) != {'host', 'address', 'mac_address'}
                        or not re.fullmatch(r'02(?::[0-9a-f]{2}){5}', item['mac_address'])
                        or not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?', item['host'])
                        or any(not label or len(label) > 63 or label.startswith('-') or label.endswith('-') for label in item['host'].split('.'))): raise ValueError()
                address = ipaddress.ip_address(item['address'])
                if (address.version != 4 or str(address) != item['address'] or address not in cidr
                        or address in {cidr.network_address, cidr.broadcast_address}): raise ValueError()
                for kind, value in [('address', item['address']), ('host', item['host']), ('mac', item['mac_address'])]:
                    if (kind, value) in seen: raise ValueError()
                    seen.add((kind, value))
        if any(('address', address) in seen for address in management): raise ValueError()
        # Una red nueva no adopta un slot legacy, esté libre o ya retirado.
        for legacy in settings.network_profiles.values():
            for item in legacy.get('instances', {}).values():
                for kind, value in [('address', str(ipaddress.ip_address(item['address']))),
                                    ('host', item['host'].lower()), ('mac', item['mac_address'].lower())]:
                    if (kind, value) in seen: raise ValueError()
        profile = profiles[network_id]
        if profile['cluster_uuid'] != cluster_uuid or node not in profile['nodes']: raise ValueError()
        profile = deepcopy(profile)
        profile['management_addresses'] = sorted(management)
        return profile, _network_hash(profile)
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
        raise _network_error() from None


async def reservar_aplicacion(db, identity, *, network_id, settings=None):
    """Asignación transaccional 011; el caller confirma antes de efectos PVE.

La identidad debe ser nueva y persistida por la admisión. TLS por identidad se
instala después por el canal privado; aquí sólo se congela la red no sensible.
"""
    from app.models.reserva_red_aplicacion import ReservaRedAplicacion
    from app.services.capacidad_service import bloqueo_capacidad
    async with bloqueo_capacidad(db):
        current = await db.scalar(select(IdentidadInfraestructura).where(IdentidadInfraestructura.id == identity.id)
            .with_for_update().execution_options(populate_existing=True))
        if current is None or current.ausencia_confirmada_at is not None: raise _network_error()
        existing = await db.scalar(select(ReservaRedAplicacion).where(ReservaRedAplicacion.identidad_id == current.id))
        if existing:
            if existing.perfil_id != network_id or existing.liberada_at is not None: raise _network_error()
            return deepcopy(existing.snapshot)
        if current.estado != 'reclamada': raise _network_error()
        profile, digest = validar_red_aplicacion(network_id, cluster_uuid=current.cluster_id, node=current.nodo, settings=settings)
        active = list((await db.scalars(select(ReservaRedAplicacion).where(ReservaRedAplicacion.liberada_at.is_(None)))).all())
        busy_addresses = {r.address for r in active if r.cluster_id == current.cluster_id}
        busy_slots = {r.slot_id for r in active if r.perfil_id == network_id}
        for slot_id, item in sorted(profile['slots'].items()):
            if slot_id in busy_slots or item['address'] in busy_addresses: continue
            instance = snapshot({**profile, 'ip_mode': 'static'}, item)
            allocation = {'schema_version': 'nap-application-network/1', 'network_profile_id': network_id,
                'network_revision': profile['revision'], 'network_sha256': digest, 'cluster_uuid': current.cluster_id,
                'slot_id': slot_id, 'resource_uuid': str(current.resource_uuid), 'instance': instance,
                'allowed_cidrs': deepcopy(profile['allowed_cidrs']),
                'management_addresses': deepcopy(profile['management_addresses'])}
            db.add(ReservaRedAplicacion(identidad_id=current.id, cluster_id=current.cluster_id,
                perfil_id=network_id, perfil_revision=profile['revision'], slot_id=slot_id,
                address=item['address'], mac=item['mac_address'], host=item['host'], snapshot=allocation))
            await db.flush()
            return deepcopy(allocation)
        raise error(409, 'red_aplicacion_agotada', 'No quedan direcciones disponibles para una nueva instancia')


async def liberar_aplicacion(db, identity, observation):
    from app.models.reserva_red_aplicacion import ReservaRedAplicacion
    from app.services.capacidad_service import bloqueo_capacidad
    from app.utils.clock import clock
    async with bloqueo_capacidad(db):
        current = await db.scalar(select(IdentidadInfraestructura).where(IdentidadInfraestructura.id == identity.id)
            .with_for_update().execution_options(populate_existing=True))
        if (current is None or current.estado != 'retirada' or current.ausencia_confirmada_at is None
                or observation.estado != 'ausente' or observation.resource_uuid != str(current.resource_uuid)):
            raise error(409, 'ausencia_no_confirmada', 'Se debe confirmar la ausencia del recurso y sus discos antes de liberar la dirección')
        row = await db.scalar(select(ReservaRedAplicacion).where(ReservaRedAplicacion.identidad_id == current.id).with_for_update())
        if row and row.liberada_at is None:
            row.liberada_at = clock.now(); await db.flush()


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
