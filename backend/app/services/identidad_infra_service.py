"""Reclamación global y propiedad demostrada, independiente del hostname."""
from dataclasses import dataclass
import hashlib
import json
import re
import secrets
from uuid import uuid4

from sqlalchemy import select

from app.config import get_settings
from app.models.identidad_infraestructura import IdentidadInfraestructura
from app.services.infraestructura_io import con_cliente, consultar, InfraNoVerificable
from app.services.inventario_service import integer, marker
from app.utils.clock import clock
from app.utils.errors import error
from app.utils.secretos import configured_keyring


def marca(identity):
    nonce = configured_keyring().decrypt(identity.nonce_cifrado, context=f'infra:{identity.resource_uuid}:nonce')
    value = {'resource_uuid': str(identity.resource_uuid), 'nonce_sha256': hashlib.sha256(nonce.encode()).hexdigest(),
            'pool': identity.pool_catedra}
    if identity.definition_sha256 and identity.bundle_sha256:
        value.update(cluster_uuid=identity.cluster_id, definition_sha256=identity.definition_sha256,
            bundle_sha256=identity.bundle_sha256)
    return value


def descripcion(identity):
    return json.dumps({'nap': marca(identity)}, sort_keys=True, separators=(',', ':'))


async def reclamar(db, operation, *, pve=None):
    """Caller mantiene lock 4001 y lease actual; commit antes de cualquier POST."""
    from app.services.capacidad_service import bloqueo_capacidad
    async with bloqueo_capacidad(db):
        if operation.identidad_infraestructura_id:
            identity = await db.get(IdentidadInfraestructura, operation.identidad_infraestructura_id)
            if identity is None or identity.ausencia_confirmada_at:
                raise error(409, 'identidad_retirada', 'La identidad histórica requiere una nueva decisión')
            return identity
        profile = get_settings().infrastructure_profile
        cluster = profile.get('cluster_id')
        destination = operation.contexto_seguro['destino']
        if not cluster or destination['nodo'] not in profile.get('nodos', {}):
            raise error(502, 'destino_no_verificable', 'Falta el perfil institucional del destino')
        observed = await consultar('get_cluster_resources', 'vm', pve=pve)
        proposed = await consultar('get_next_vmid', pve=pve)
        if observed.estado != 'presente' or proposed.estado != 'presente':
            raise InfraNoVerificable()
        busy = {integer(row['vmid'], minimum=1) for row in observed.valor}
        busy.update((await db.scalars(select(IdentidadInfraestructura.vmid).where(
            IdentidadInfraestructura.cluster_id == cluster,
            IdentidadInfraestructura.ausencia_confirmada_at.is_(None)))).all())
        vmid = integer(proposed.valor, minimum=100)
        while vmid in busy and vmid < 999999999:
            vmid += 1
        if vmid in busy or vmid > 999999999:
            raise InfraNoVerificable()
        resource_uuid, nonce = uuid4(), secrets.token_urlsafe(32)
        product = operation.contexto_seguro['asignacion'].get('product')
        if product in {'postgresql', 'bookstack', 'drawio'} or operation.contexto_seguro['asignacion'].get('origen') == 'proxmox_iaas':
            from app.services.reserva_red_service import reservar
            network_id = operation.contexto_seguro.get('preparacion_validada', {}).get('network_profile_id')
            resource_uuid, allocation = await reservar(db, network_id=network_id, product=product, node=destination['nodo'])
            operation.contexto_seguro = {**operation.contexto_seguro, 'red_reservada': allocation}
        identity = IdentidadInfraestructura(cluster_id=cluster, vmid=vmid, nodo=destination['nodo'],
            pool_catedra=f"catedra-{operation.contexto_seguro['catedra_id']}", resource_uuid=resource_uuid,
            nonce_cifrado=configured_keyring().encrypt(nonce, context=f'infra:{resource_uuid}:nonce'),
            definition_sha256=operation.contexto_seguro['asignacion'].get('definition_sha256'),
            bundle_sha256=operation.contexto_seguro['asignacion'].get('bundle_sha256'),
            pedido_alta_id=operation.pedido_id, estado='reclamada', claimed_at=clock.now())
        db.add(identity)
        await db.flush()
        operation.identidad_infraestructura_id = identity.id
        return identity


@dataclass(frozen=True)
class Propiedad:
    estado: str
    resource_uuid: str
    config: dict | None = None
    status: str | None = None
    metricas: dict | None = None


async def observar(identity, *, pve=None):
    expected, vmid, node = marca(identity), identity.vmid, identity.nodo
    resource_uuid = str(identity.resource_uuid)
    profile = get_settings().model_copy(deep=True).infrastructure_profile
    if identity.cluster_id != profile.get('cluster_id'):
        raise InfraNoVerificable()

    def inspect(client):
        resources = client.get_cluster_resources('vm')
        if not isinstance(resources, list):
            raise InfraNoVerificable()
        matches = [row for row in resources if integer(row['vmid'], minimum=1) == vmid]
        if len(matches) > 1:
            raise InfraNoVerificable()
        if not matches:
            # Un resumen filtrado por permisos no basta. nextid(vmid=...) usa
            # el registro global y falla si está ocupado, incluso siendo QEMU.
            nodes = client.get_nodes()
            if not nodes or any(row.get('status') != 'online' for row in nodes) or node not in {row['node'] for row in nodes}:
                raise InfraNoVerificable()
            if integer(client.check_vmid_available(vmid), minimum=1) != vmid:
                raise InfraNoVerificable()
            storages = profile.get('nodos', {}).get(node, {}).get('storages', [])
            if not storages:
                raise InfraNoVerificable()
            for storage in storages:
                volumes = client.get_storage_content(node, storage)
                if not isinstance(volumes, list) or any(re.search(
                    rf'(?:vm-|subvol-){vmid}-|[:/]{vmid}/', entry['volid']) for entry in volumes):
                    raise InfraNoVerificable()
            return Propiedad('ausente', resource_uuid)
        resource = matches[0]
        if resource.get('type') != 'lxc' or resource.get('node') != node:
            return Propiedad('ajena', resource_uuid)
        config = client.get_lxc_config(node, vmid)
        if marker(config) != expected or resource.get('pool') != expected['pool']:
            return Propiedad('ajena', resource_uuid)
        status = client.get_lxc_status(node, vmid)
        if not isinstance(status, dict) or status.get('status') not in {'running', 'stopped'}:
            raise InfraNoVerificable()
        return Propiedad('propia', resource_uuid, config, status['status'], dict(status))
    return await con_cliente(inspect, pve=pve)


def retirar(identity, observation):
    if observation.estado != 'ausente' or observation.resource_uuid != str(identity.resource_uuid):
        raise ValueError('Retirar requiere ausencia confirmada de la misma identidad')
    identity.estado, identity.ausencia_confirmada_at = 'retirada', clock.now()


async def reclamar_ensayo(db,resource,artifact,*,pve=None):
    """Misma unicidad global que producción, con dueño institucional distinto."""
    from app.models.compromiso_capacidad import CompromisoCapacidad
    from app.services.capacidad_service import bloqueo_capacidad
    async with bloqueo_capacidad(db):
        if resource.identidad_infraestructura_id:
            identity=await db.get(IdentidadInfraestructura,resource.identidad_infraestructura_id)
            if not identity or identity.ausencia_confirmada_at:raise error(409,'identidad_retirada','El recurso requiere otra decisión')
            return identity
        destination=resource.destino_snapshot;cluster=get_settings().infrastructure_profile.get('cluster_id')
        if not cluster:raise error(409,'cluster_no_preparado','Falta identidad institucional del clúster')
        pools=await consultar('list_pools',pve=pve)
        if pools.estado!='presente' or destination['pool'] not in {p['poolid'] for p in pools.valor}:
            raise error(409,'pool_ensayo_no_preparado','Prepará el pool institucional de ensayos')
        observed=await consultar('get_cluster_resources','vm',pve=pve)
        proposed=await consultar('get_next_vmid',pve=pve)
        if observed.estado!='presente' or proposed.estado!='presente':raise InfraNoVerificable()
        busy={integer(r['vmid'],minimum=1) for r in observed.valor}
        busy.update((await db.scalars(select(IdentidadInfraestructura.vmid).where(IdentidadInfraestructura.cluster_id==cluster,IdentidadInfraestructura.ausencia_confirmada_at.is_(None)))).all())
        vmid=integer(proposed.valor,minimum=100)
        while vmid in busy and vmid<999999999:vmid+=1
        if vmid in busy:raise InfraNoVerificable()
        from app.services.reserva_red_service import reservar
        from app.schemas.definicion import digest
        uid,allocation=await reservar(db,network_id=destination['network_profile_id'],product='drawio',node=destination['nodo'])
        nonce=secrets.token_urlsafe(32)
        identity=IdentidadInfraestructura(cluster_id=cluster,vmid=vmid,nodo=destination['nodo'],pool_catedra=destination['pool'],
            recurso_ensayo_id=resource.id,resource_uuid=uid,nonce_cifrado=configured_keyring().encrypt(nonce,context=f'infra:{uid}:nonce'),
            definition_sha256=digest(artifact.manifest),bundle_sha256=artifact.bundle_sha256)
        db.add(identity);await db.flush()
        resource.identidad_infraestructura_id=identity.id
        resource.destino_snapshot={**destination,'red_reservada':allocation}
        ledger=await db.scalar(select(CompromisoCapacidad).where(CompromisoCapacidad.recurso_ensayo_id==resource.id,CompromisoCapacidad.liberado_at.is_(None)).with_for_update())
        if not ledger:raise error(409,'reserva_no_disponible','Falta reserva del recurso de ensayo')
        ledger.identidad_infraestructura_id=identity.id
        return identity
