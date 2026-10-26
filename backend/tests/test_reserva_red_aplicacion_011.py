from copy import deepcopy
from uuid import uuid4

from fastapi import HTTPException
import pytest

from app.config import get_settings
from app.models.identidad_infraestructura import IdentidadInfraestructura
from app.services.reserva_red_service import validar_red_aplicacion, reservar_aplicacion, liberar_aplicacion
from app.services.identidad_infra_service import Propiedad, retirar
from app.utils.secretos import configured_keyring


@pytest.fixture
def red_aplicaciones_011(monkeypatch):
    settings = get_settings(); cluster = str(uuid4())
    profile = {'schema_version': 'nap-application-network/1', 'revision': 1,
        'cluster_uuid': cluster, 'nodes': ['pve1'], 'bridge': 'vmbr0',
        'allowed_cidrs': ['10.80.0.0/24'], 'client_cidrs': ['10.90.0.0/24'],
        'static_cidr': '10.80.0.0/24', 'gateway': '10.80.0.1',
        'management_addresses': ['10.80.0.2'],
        'slots': {f'slot-{n}': {'address': f'10.80.0.{n+10}', 'mac_address': f'02:00:00:00:00:{n:02x}',
                              'host': f'app{n}.example.edu'} for n in (1,2)}}
    monkeypatch.setattr(settings, 'application_network_profiles', {'app-network': profile})
    monkeypatch.setattr(settings, 'network_profiles', {})
    return profile


async def new_identity_011(db, cluster, vmid):
    resource = uuid4()
    row = IdentidadInfraestructura(cluster_id=cluster, nodo='pve1', vmid=vmid, pool_catedra='fixture',
        resource_uuid=resource, nonce_cifrado=configured_keyring().encrypt(str(uuid4()), context=f'infra:{resource}:nonce'))
    db.add(row); await db.flush(); return row


@pytest.mark.parametrize('bad', ['management', 'gateway', 'broadcast', 'legacy', 'cross-profile',
    'foreign-cluster', 'foreign-node', 'duplicate-mac', 'host-command'])
def test_network_rejects_management_legacy_overlap_and_unapproved_targets(red_aplicaciones_011, bad, monkeypatch):
    settings = get_settings(); profile = red_aplicaciones_011
    if bad == 'management': profile['slots']['slot-1']['address'] = '10.80.0.2'
    if bad == 'gateway': profile['slots']['slot-1']['address'] = '10.80.0.1'
    if bad == 'broadcast': profile['slots']['slot-1']['address'] = '10.80.0.255'
    if bad == 'legacy': monkeypatch.setattr(settings, 'network_profiles', {'old': {'instances': {str(uuid4()): deepcopy(profile['slots']['slot-1'])}}})
    if bad == 'cross-profile': settings.application_network_profiles['duplicate'] = deepcopy(profile)
    if bad == 'duplicate-mac': profile['slots']['slot-2']['mac_address'] = profile['slots']['slot-1']['mac_address']
    if bad == 'host-command': profile['slots']['slot-1']['host'] = '$(unsafe).example.edu'
    cluster = str(uuid4()) if bad == 'foreign-cluster' else profile['cluster_uuid']
    node = 'another' if bad == 'foreign-node' else 'pve1'
    with pytest.raises(HTTPException) as caught:
        validar_red_aplicacion('app-network', cluster_uuid=cluster, node=node)
    assert caught.value.status_code == 409


async def test_slots_are_idempotent_exhaustion_does_not_create_an_allocation(db, red_aplicaciones_011):
    cluster = red_aplicaciones_011['cluster_uuid']
    identities = [await new_identity_011(db, cluster, vmid) for vmid in (500,501,502)]
    first = await reservar_aplicacion(db, identities[0], network_id='app-network')
    assert first == await reservar_aplicacion(db, identities[0], network_id='app-network')
    second = await reservar_aplicacion(db, identities[1], network_id='app-network')
    assert first['instance']['address'] != second['instance']['address']
    assert first['resource_uuid'] != second['resource_uuid']
    with pytest.raises(HTTPException) as caught:
        await reservar_aplicacion(db, identities[2], network_id='app-network')
    assert caught.value.detail['codigo'] == 'red_aplicacion_agotada'
    assert first['instance']['static_ip']['cidr'] == '10.80.0.11/24'


async def test_release_requires_absence_of_same_identity_and_preserves_old_row(db, red_aplicaciones_011):
    from sqlalchemy import select, func
    from app.models.reserva_red_aplicacion import ReservaRedAplicacion
    identity = await new_identity_011(db, red_aplicaciones_011['cluster_uuid'], 500)
    original = await reservar_aplicacion(db, identity, network_id='app-network')
    with pytest.raises(HTTPException): await liberar_aplicacion(db, identity, Propiedad('propia', str(identity.resource_uuid)))
    absent = Propiedad('ausente', str(identity.resource_uuid))
    with pytest.raises(HTTPException): await liberar_aplicacion(db, identity, absent)
    retirar(identity, absent)
    await liberar_aplicacion(db, identity, absent)
    replacement = await new_identity_011(db, identity.cluster_id, 501)
    reused = await reservar_aplicacion(db, replacement, network_id='app-network')
    assert original['slot_id'] == reused['slot_id'] and original['resource_uuid'] != reused['resource_uuid']
    assert await db.scalar(select(func.count()).select_from(ReservaRedAplicacion)) == 2
    row = await db.scalar(select(ReservaRedAplicacion).where(ReservaRedAplicacion.identidad_id == identity.id))
    assert row.liberada_at is not None
