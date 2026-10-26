"""Capacidad por nodo/pool: unión conservadora de inventario y ledger durable."""
import hashlib
from datetime import datetime, timedelta
import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pedido import Pedido, EstadoPedido, TipoPedido
from app.models.servicio import Servicio, EstadoServicio
from app.models.compromiso_capacidad import CompromisoCapacidad
from app.models.identidad_infraestructura import IdentidadInfraestructura
from app.services import scheduler, historial_service
from app.services import inventario_service
from app.services.proxmox_client import get_proxmox_client
from app.utils.clock import clock, db_utc
from app.utils.errors import error
from app.utils.secretos import configured_keyring, SecretError

logger = logging.getLogger(__name__)
RESERVA_VIGENCIA = timedelta(hours=24)
CLAVE_BLOQUEO = 4001
GIB = 1024 ** 3


class BloqueoCapacidad:
    """PostgreSQL serializa procesos; SQLite solo permite pruebas de contrato."""
    def __init__(self, db):
        self.db = db
    async def __aenter__(self):
        if self.db.bind.dialect.name == 'postgresql':
            await self.db.execute(select(func.pg_advisory_xact_lock(CLAVE_BLOQUEO)))
        return self
    async def __aexit__(self, *exc):
        return False


def bloqueo_capacidad(db):
    return BloqueoCapacidad(db)


def _owned(resource, identity, cluster_id):
    if not identity or identity.ausencia_confirmada_at or not identity.ownership_verificada_at:
        return False
    mark = resource['marca']
    if not mark or identity.cluster_id != cluster_id or identity.nodo != resource['nodo'] or identity.vmid != resource['vmid']:
        return False
    try:
        nonce = configured_keyring().decrypt(identity.nonce_cifrado, context=f'infra:{identity.resource_uuid}:nonce')
        return (mark['resource_uuid'] == str(identity.resource_uuid) and mark['pool'] == identity.pool_catedra
                and resource['pool'] == identity.pool_catedra
                and mark['nonce_sha256'] == hashlib.sha256(nonce.encode()).hexdigest())
    except (SecretError, ValueError, TypeError):
        return False


def _vector(vcpus=0, ram_mb=0, disk_bytes=0):
    return {'vcpus': vcpus, 'ram_mb': ram_mb, 'disk_gb': disk_bytes // GIB, 'storage_gb': disk_bytes // GIB, 'disk_bytes': disk_bytes}


async def panorama(db, pve=None, *, destino=None, inventario=None):
    inventory = inventario or await inventario_service.leer(pve)
    commitments = list((await db.scalars(select(CompromisoCapacidad).where(CompromisoCapacidad.liberado_at.is_(None)))).all())
    identities = {entry.id: entry for entry in (await db.scalars(select(IdentidadInfraestructura))).all()}
    held_identity_ids = [entry.identidad_infraestructura_id for entry in commitments if entry.identidad_infraestructura_id]
    if len(held_identity_ids) != len(set(held_identity_ids)):
        raise error(502, 'compromisos_inconsistentes', 'Reconciliar compromisos de infraestructura antes de admitir cambios')
    resource_owner = {}
    for entry in commitments:
        identity = identities.get(entry.identidad_infraestructura_id)
        resource = inventory['recursos'].get(identity.vmid) if identity else None
        if resource and _owned(resource, identity, inventory['cluster_id']):
            resource_owner[identity.vmid] = entry
    observed = {node: {'vcpus': 0, 'ram_mb': 0} for node in inventory['nodos']}
    external = {node: {'vcpus': 0, 'ram_mb': 0} for node in inventory['nodos']}
    extra = {node: {'vcpus': 0, 'ram_mb': 0} for node in inventory['nodos']}
    pending_disk = {scope: 0 for scope in inventory['storages']}
    own_volumes = set()
    for resource in inventory['recursos'].values():
        node = resource['nodo']
        if node in observed:
            for field in ['vcpus', 'ram_mb']:
                observed[node][field] += resource[field]
                if resource['vmid'] not in resource_owner:
                    external[node][field] += resource[field]
        if resource['vmid'] in resource_owner:
            own_volumes.update(resource['volumenes'])
    for entry in commitments:
        identity = identities.get(entry.identidad_infraestructura_id)
        resource = inventory['recursos'].get(identity.vmid) if identity and identity.vmid in resource_owner else None
        current_scope = inventory['destinos'].get((entry.nodo, entry.storage_id))
        if current_scope is not None and current_scope != entry.storage_scope:
            raise error(502, 'scope_comprometido_cambiado', 'Reconciliar el perfil de almacenamiento con los compromisos existentes')
        if entry.nodo in extra:
            for field, quantity in [('vcpus', entry.vcpus_retenidos), ('ram_mb', entry.ram_mb_retenida)]:
                extra[entry.nodo][field] += max(0, quantity - (resource[field] if resource else 0))
        represented = sum(size for (scope, _), size in resource['volumenes'].items() if scope == entry.storage_scope) if resource else 0
        if entry.storage_scope in pending_disk:
            pending_disk[entry.storage_scope] += max(0, entry.disk_bytes_retenidos - represented)
    destinations = []
    for (node, storage_id), scope in sorted(inventory['destinos'].items()):
        hardware, storage = inventory['nodos'][node], inventory['storages'][scope]
        logical_free = storage['capacidad_logica_bytes'] - storage['margen_logico_bytes'] - storage['asignado_bytes'] - pending_disk[scope]
        physical_free = storage['fisico_libre_bytes'] - storage['margen_fisico_bytes'] - pending_disk[scope]
        cpu = observed[node]['vcpus'] + extra[node]['vcpus']
        ram = observed[node]['ram_mb'] + extra[node]['ram_mb']
        external_disk = storage['asignado_bytes'] - sum(size for key, size in inventory['volumenes'].items() if key in own_volumes and key[0] == scope)
        destinations.append({'destino': {'nodo': node, 'storage': storage_id}, 'storage_scope': scope,
            'fisica': _vector(hardware['vcpus'], hardware['ram_mb'], storage['total_bytes']),
            'margen': _vector(hardware['margen_vcpus'], hardware['margen_ram_mb'], storage['margen_fisico_bytes']),
            'ram_fisica_libre_mb': hardware['ram_fisica_libre_mb'],
            'desplegado': _vector(observed[node]['vcpus'], observed[node]['ram_mb'], storage['asignado_bytes']),
            'externo': _vector(external[node]['vcpus'], external[node]['ram_mb'], external_disk),
            'reservado': _vector(extra[node]['vcpus'], extra[node]['ram_mb'], pending_disk[scope]),
            'comprometido': _vector(cpu, ram, storage['asignado_bytes'] + pending_disk[scope]),
            'libre': _vector(hardware['vcpus'] - hardware['margen_vcpus'] - cpu,
                hardware['ram_mb'] - hardware['margen_ram_mb'] - ram, min(logical_free, physical_free)),
            'storage_logico_libre_bytes': logical_free, 'storage_fisico_libre_bytes': physical_free})
    ledger_snapshot = [{key: str(getattr(row, key)) for key in ['id', 'pedido_id', 'recurso_ensayo_id', 'servicio_id', 'identidad_infraestructura_id',
        'nodo', 'storage_scope', 'vcpus_retenidos', 'ram_mb_retenida', 'disk_bytes_retenidos', 'estado', 'revision', 'expira_at']}
        for row in sorted(commitments, key=lambda row: str(row.id))]
    # La aprobación vincula asignaciones/configuración, no telemetría que cambia
    # con cada lectura. El saldo físico se vuelve a comprobar bajo lock al aprobar.
    stable_inventory = {**inventory,
        'nodos': {key: {field: value for field, value in row.items() if field != 'ram_fisica_libre_mb'}
                  for key, row in inventory['nodos'].items()},
        'storages': {key: {field: value for field, value in row.items() if field != 'fisico_libre_bytes'}
                     for key, row in inventory['storages'].items()}}
    fingerprint = inventario_service.fingerprint({'inventario': stable_inventory, 'compromisos': ledger_snapshot})
    if destino is not None:
        if hasattr(destino, 'model_dump'):
            destino = destino.model_dump(mode='json')
        value = next((row for row in destinations if row['destino'] == destino), None)
        if value is None:
            raise error(422, 'destino_no_permitido', 'Elegí un nodo y almacenamiento LXC elegibles')
        return {**value, 'capacidad_token': fingerprint}
    # Totales solo informativos: la admisión consulta siempre el destino concreto.
    physical_disk = sum(value['total_bytes'] for value in inventory['storages'].values())
    deployed_disk = sum(value['asignado_bytes'] for value in inventory['storages'].values())
    reserved_disk = sum(pending_disk.values())
    cpus = sum(value['vcpus'] for value in inventory['nodos'].values())
    ram = sum(value['ram_mb'] for value in inventory['nodos'].values())
    used_cpu = sum(value['vcpus'] for value in observed.values())
    used_ram = sum(value['ram_mb'] for value in observed.values())
    reserved_cpu = sum(value['vcpus'] for value in extra.values())
    reserved_ram = sum(value['ram_mb'] for value in extra.values())
    risk_ram = int(await db.scalar(select(func.coalesce(func.sum(Servicio.ram_asignada_mb), 0))
        .where(Servicio.estado == EstadoServicio.PAUSED, Servicio.deleted_at.is_(None))))
    return {'destinos': destinations, 'fisica': _vector(cpus, ram, physical_disk),
        'desplegado': _vector(used_cpu, used_ram, deployed_disk),
        'reservado': _vector(reserved_cpu, reserved_ram, reserved_disk),
        'comprometido': _vector(used_cpu + reserved_cpu, used_ram + reserved_ram, deployed_disk + reserved_disk),
        'libre': _vector(cpus - used_cpu - reserved_cpu - sum(value['margen_vcpus'] for value in inventory['nodos'].values()),
            ram - used_ram - reserved_ram - sum(value['margen_ram_mb'] for value in inventory['nodos'].values()),
            sum(min(value['capacidad_logica_bytes'] - value['margen_logico_bytes'] - value['asignado_bytes'] - pending_disk[scope],
                    value['fisico_libre_bytes'] - value['margen_fisico_bytes'] - pending_disk[scope]) for scope, value in inventory['storages'].items())),
        'ram_en_riesgo_mb': risk_ram, 'capacidad_token': fingerprint}


def costo_de(template):
    return {'vcpus': template.default_vcpus, 'ram_mb': template.default_ram_mb, 'storage_gb': template.default_disk_gb} if template else {'vcpus': 0, 'ram_mb': 0, 'storage_gb': 0}


def excede(libre, costo):
    return any(costo[key] > libre[key] for key in costo)


async def consumo_de_catedra(db, catedra_id):
    result = await db.execute(select(func.coalesce(func.sum(Servicio.vcpus_asignados), 0),
        func.coalesce(func.sum(Servicio.ram_asignada_mb), 0), func.coalesce(func.sum(Servicio.disk_asignado_gb), 0))
        .where(Servicio.catedra_id == catedra_id, Servicio.deleted_at.is_(None)))
    cpus, ram, disk = result.one()
    return {'vcpus': int(cpus), 'ram_mb': int(ram), 'storage_gb': int(disk)}


async def expirar_reservas(db):
    """Cada liberación se revalida bajo el mismo lock que aprobar/desplegar."""
    from fastapi import HTTPException
    from app.services.admision_service import liberar
    ids = list((await db.scalars(select(CompromisoCapacidad.pedido_id).where(
        CompromisoCapacidad.pedido_id.is_not(None), CompromisoCapacidad.estado == 'reservado', CompromisoCapacidad.liberado_at.is_(None),
        CompromisoCapacidad.expira_at <= clock.now()).order_by(CompromisoCapacidad.pedido_id))).all())
    await db.commit()
    affected = []
    for identity in ids:
        try:
            result = await liberar(db, identity, actor=None, motivo='Reserva de capacidad vencida antes de dispatch', expirar=True)
            await db.commit()
            if not result.replayed:
                affected.append(identity)
        except HTTPException as exc:
            await db.rollback()
            if exc.status_code != 409:
                raise
    return {'afectados': len(affected), 'detalle': affected}


scheduler.registrar('expirar_reservas', expirar_reservas, cada_minutos=1)
