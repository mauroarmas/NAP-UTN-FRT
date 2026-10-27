"""Inventario normalizado: asignación configurada, volúmenes y pools elegibles."""
from decimal import Decimal
import hashlib
import json
import re

from app.config import get_settings
from app.schemas.inventario import PerfilInfraestructura
from app.utils.errors import error

GIB, MIB = 1024 ** 3, 1024 ** 2


def integer(value, *, minimum=0):
    if type(value) is str and value.isascii() and value.isdigit():
        value = int(value)
    if type(value) is not int or not minimum <= value <= 2**63 - 1:
        raise ValueError('Cantidad de inventario incompleta')
    return value


def disk_size(value):
    match = re.fullmatch(r'(\d+(?:\.\d+)?)([KMGT]?)', str(value))
    if not match:
        raise ValueError('Tamaño de volumen no verificable')
    multiplier = {'': 1, 'K': 1024, 'M': MIB, 'G': GIB, 'T': 1024**4}[match[2]]
    amount = Decimal(match[1]) * multiplier
    if amount != amount.to_integral_value():
        raise ValueError('Tamaño fraccionario en bytes')
    return integer(int(amount))


def marker(config):
    raw = config.get('description', '')
    if not isinstance(raw, str) or len(raw.encode()) > 4096:
        return None
    try:
        value = json.loads(raw)
        nap = value['nap']
        legacy = {'resource_uuid', 'nonce_sha256', 'pool'}
        if not isinstance(nap, dict) or set(nap) not in [legacy, legacy | {'cluster_uuid', 'definition_sha256', 'bundle_sha256'}]:
            return None
        return nap
    except (ValueError, TypeError, KeyError):
        return None


def _volume_references(config, resource_type):
    pattern = r'(rootfs|mp\d+)' if resource_type == 'lxc' else r'(ide|sata|scsi|virtio)\d+'
    for name, value in sorted(config.items()):
        if not re.fullmatch(pattern, name) or not isinstance(value, str):
            continue
        parts = value.split(',')
        volume = parts[0].removeprefix('volume=')
        if ':' not in volume or any(part == 'media=cdrom' for part in parts):
            continue  # Bind mount ajeno al storage o medio óptico.
        storage, suffix = volume.split(':', 1)
        declared = next((part.split('=', 1)[1] for part in parts if part.startswith('size=')), None)
        yield storage, suffix, disk_size(declared) if declared else None


def observar(pve, profile=None):
    try:
        profile = PerfilInfraestructura.model_validate(profile or get_settings().infrastructure_profile)
        raw_nodes = pve.get_nodes()
        if not isinstance(raw_nodes, list) or len({row['node'] for row in raw_nodes}) != len(raw_nodes):
            raise ValueError('Inventario de nodos inválido')
        online = {row['node']: row for row in raw_nodes if row.get('status') == 'online'}
        nodes, storages, volumes, paths = {}, {}, {}, {}
        for node_id, limits in sorted(profile.nodos.items()):
            if node_id not in online:
                continue
            raw = online[node_id]
            cpu, memory = integer(raw.get('maxcpu'), minimum=1), integer(raw.get('maxmem'), minimum=1)
            used_memory = integer(raw.get('mem'))
            if used_memory > memory or limits.margen_vcpus >= cpu or limits.margen_ram_mb * MIB >= memory:
                raise ValueError('Margen o estado de nodo inconsistente')
            nodes[node_id] = {'vcpus': cpu, 'ram_mb': memory // MIB, 'ram_fisica_libre_mb': (memory - used_memory) // MIB,
                'margen_vcpus': limits.margen_vcpus, 'margen_ram_mb': limits.margen_ram_mb}
            rows = pve.get_node_storage(node_id)
            if not isinstance(rows, list):
                raise ValueError('Almacenamientos no observables')
            for storage_id in sorted(limits.storages):
                candidates = [row for row in rows if row.get('storage') == storage_id]
                if len(candidates) != 1:
                    raise ValueError('Almacenamiento no verificable')
                raw_storage = candidates[0]
                specification = profile.almacenamientos[storage_id]
                if raw_storage.get('active') not in [1, True] or raw_storage.get('enabled') not in [1, True]:
                    continue
                content = set(str(raw_storage.get('content', '')).split(','))
                if 'rootdir' not in content:
                    continue
                shared = raw_storage.get('shared')
                if type(shared) is bool:
                    shared = int(shared)
                if integer(shared) != int(specification.shared):
                    raise ValueError('El scope real no coincide con el inventario autorizado')
                total, free = integer(raw_storage.get('total'), minimum=1), integer(raw_storage.get('avail'))
                if free > total:
                    raise ValueError('Espacio de almacenamiento inconsistente')
                pool = specification.pool_id or storage_id
                scope = f'shared:{pool}' if specification.shared else f'node:{node_id}:{pool}'
                paths[(node_id, storage_id)] = scope
                logical_total = specification.capacidad_logica_bytes or total
                value = {'scope': scope, 'total_bytes': total, 'fisico_libre_bytes': free,
                    'capacidad_logica_bytes': logical_total, 'margen_logico_bytes': specification.margen_logico_bytes,
                    'margen_fisico_bytes': specification.margen_fisico_bytes, 'shared': specification.shared}
                if scope in storages:
                    # Un pool compartido tiene un solo saldo; conservar la observación menor.
                    for field in ['total_bytes', 'fisico_libre_bytes', 'capacidad_logica_bytes']:
                        value[field] = min(value[field], storages[scope][field])
                storages[scope] = value
                entries = pve.get_storage_content(node_id, storage_id)
                if not isinstance(entries, list):
                    raise ValueError('Volúmenes no verificables')
                for volume in entries:
                    if volume.get('content') not in {'images', 'rootdir'}:
                        continue
                    volid = volume.get('volid')
                    if not isinstance(volid, str) or not volid.startswith(storage_id + ':'):
                        raise ValueError('Volumen sin identidad de storage')
                    key = (scope, volid.split(':', 1)[1])
                    volumes[key] = max(volumes.get(key, 0), integer(volume.get('size'), minimum=1))
        if not paths:
            raise ValueError('No hay destinos LXC elegibles')
        resources = {}
        raw_resources = pve.get_cluster_resources('vm')
        if not isinstance(raw_resources, list):
            raise ValueError('Recursos no verificables')
        for raw in raw_resources:
            kind, vmid, node = raw.get('type'), integer(raw.get('vmid'), minimum=1), raw.get('node')
            if kind not in {'lxc', 'qemu'} or not isinstance(node, str) or vmid in resources:
                raise ValueError('Identidad de recurso inválida')
            config = pve.get_lxc_config(node, vmid) if kind == 'lxc' else pve.get_qemu_config(node, vmid)
            if not isinstance(config, dict):
                raise ValueError('Configuración no verificable')
            cpus = integer(raw.get('maxcpu', config.get('cores')), minimum=1)
            if kind == 'qemu' and 'maxcpu' not in raw:
                cpus *= integer(config.get('sockets', 1), minimum=1)
            ram_bytes = integer(raw['maxmem'], minimum=1) if 'maxmem' in raw else integer(config.get('memory'), minimum=1) * MIB
            # Solo un stopped explícito libera cómputo observado. Unknown conserva.
            active = raw.get('status') != 'stopped'
            refs = {}
            for storage_id, suffix, declared in _volume_references(config, kind):
                scope = paths.get((node, storage_id))
                if scope is None:
                    if storage_id in profile.almacenamientos and profile.almacenamientos[storage_id].shared:
                        specification = profile.almacenamientos[storage_id]
                        scope = f'shared:{specification.pool_id or storage_id}'
                    else:
                        continue
                key = (scope, suffix)
                if key not in volumes:
                    raise ValueError('Falta observación de un volumen configurado')
                if declared:
                    volumes[key] = max(volumes[key], declared)
                refs[key] = volumes[key]
            resources[vmid] = {'vmid': vmid, 'tipo': kind, 'nodo': node, 'estado': raw.get('status', 'unknown'),
                'configurado_vcpus': cpus, 'configurado_ram_mb': (ram_bytes + MIB - 1) // MIB,
                'vcpus': cpus if active else 0, 'ram_mb': (ram_bytes + MIB - 1) // MIB if active else 0,
                'volumenes': refs, 'pool': raw.get('pool'), 'marca': marker(config)}
        for scope, storage in storages.items():
            storage['asignado_bytes'] = sum(size for (volume_scope, _), size in volumes.items() if volume_scope == scope)
        value = {'cluster_id': profile.cluster_id, 'nodos': nodes, 'storages': storages, 'destinos': paths,
                 'recursos': resources, 'volumenes': volumes, 'perfil': profile.model_dump(mode='json')}
        return value
    except Exception:
        raise error(502, 'capacidad_no_verificable', 'No se pudo verificar el inventario y sus destinos autorizados', reintentable=True) from None


async def leer(pve=None):
    from app.services.infraestructura_io import con_cliente, InfraNoVerificable
    profile = get_settings().model_copy(deep=True).infrastructure_profile
    try:
        return await con_cliente(observar, profile, pve=pve)
    except InfraNoVerificable:
        raise error(502, 'capacidad_no_verificable', 'No se pudo verificar el inventario y sus destinos autorizados', reintentable=True) from None


def canonical_snapshot(value):
    """Claves de volumen/destino estables para hash; nunca incluye secretos PVE."""
    def normalize(item):
        if isinstance(item, dict):
            return {json.dumps(key, ensure_ascii=False, separators=(',', ':')) if isinstance(key, tuple) else str(key): normalize(child)
                    for key, child in sorted(item.items(), key=lambda row: str(row[0]))}
        if isinstance(item, list):
            return [normalize(child) for child in item]
        return item
    return normalize(value)


def fingerprint(value):
    return hashlib.sha256(json.dumps(canonical_snapshot(value), sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
