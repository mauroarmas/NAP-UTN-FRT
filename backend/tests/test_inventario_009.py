from copy import deepcopy
import pytest

from app.services.inventario_service import observar
from tests.capacity_helpers import perfil_capacidad, GIB


def test_shared_storage_is_one_pool_even_when_visible_on_two_nodes(proxmox, perfil_capacidad):
    perfil_capacidad['nodos']['pve2'] = deepcopy(perfil_capacidad['nodos']['pve1'])
    perfil_capacidad['almacenamientos']['local-lvm']['shared'] = True
    proxmox.nodos.append({**proxmox.nodos[0], 'node': 'pve2'})
    proxmox.storages[0]['shared'] = 1
    proxmox.storages.append({**proxmox.storages[0], 'node': 'pve2'})
    volume = {'volid': 'local-lvm:vm-900-disk-0', 'size': 10 * GIB, 'content': 'rootdir'}
    for node in ['pve1', 'pve2']:
        proxmox.contenidos_storage[(node, 'local-lvm')] = [volume]
    value = observar(proxmox)
    assert len(value['storages']) == 1
    assert value['storages']['shared:local-lvm']['asignado_bytes'] == 10 * GIB
    assert len(value['destinos']) == 2


def test_local_storage_with_same_name_on_two_nodes_is_separate(proxmox, perfil_capacidad):
    perfil_capacidad['nodos']['pve2'] = deepcopy(perfil_capacidad['nodos']['pve1'])
    proxmox.nodos.append({**proxmox.nodos[0], 'node': 'pve2'})
    proxmox.storages.append({**proxmox.storages[0], 'node': 'pve2'})
    proxmox.contenidos_storage[('pve2', 'local-lvm')] = []
    value = observar(proxmox)
    assert set(value['storages']) == {'node:pve1:local-lvm', 'node:pve2:local-lvm'}


@pytest.mark.parametrize('content', ['backup', 'iso,vztmpl'])
def test_storage_without_rootdir_is_not_a_destination(proxmox, perfil_capacidad, content):
    from fastapi import HTTPException
    proxmox.storages[0]['content'] = content
    with pytest.raises(HTTPException) as failed:
        observar(proxmox)
    assert failed.value.status_code == 502
