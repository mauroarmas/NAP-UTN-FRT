import pytest
from sqlalchemy import select

from app.models.operacion_infraestructura import OperacionInfraestructura
from app.models.identidad_infraestructura import IdentidadInfraestructura
from app.services import identidad_infra_service as identities
from tests.capacity_helpers import perfil_capacidad, materializado
from tests.test_operaciones_recuperacion import queued


async def test_claim_is_stable_and_skips_foreign_global_vmid(client, db, proxmox, perfil_capacidad, catedra, usuario_catedra, template, auth_admin):
    await queued(client, db, catedra, usuario_catedra, template, auth_admin)
    operation = await db.scalar(select(OperacionInfraestructura))
    proxmox.recursos.append({'type': 'qemu', 'node': 'pve1', 'vmid': 100})
    identity = await identities.reclamar(db, operation, pve=proxmox)
    await db.commit()
    again = await identities.reclamar(db, operation, pve=proxmox)
    assert again.id == identity.id and identity.vmid != 100
    assert identity.resource_uuid and identity.nonce_cifrado.startswith('v1:')
    assert not proxmox.creados


async def test_hostname_never_proves_ownership(db, proxmox, perfil_capacidad, catedra, usuario_catedra, template):
    service, ledger = await materializado(db, proxmox, catedra, usuario_catedra, template)
    identity = await db.get(IdentidadInfraestructura, service.identidad_infraestructura_id)
    assert (await identities.observar(identity, pve=proxmox)).estado == 'propia'
    proxmox.configuraciones[('pve1', identity.vmid)]['description'] = 'Mismo hostname, sin marca propia'
    observation = await identities.observar(identity, pve=proxmox)
    assert observation.estado == 'ajena'
    with pytest.raises(ValueError):
        identities.retirar(identity, observation)
    assert identity.ausencia_confirmada_at is None


async def test_failure_does_not_release_identity(db, proxmox, perfil_capacidad, catedra, usuario_catedra, template):
    service, ledger = await materializado(db, proxmox, catedra, usuario_catedra, template)
    identity = await db.get(IdentidadInfraestructura, service.identidad_infraestructura_id)
    proxmox.fallar_recursos = TimeoutError()
    from app.services.infraestructura_io import InfraNoVerificable
    with pytest.raises(InfraNoVerificable):
        await identities.observar(identity, pve=proxmox)
    assert identity.ausencia_confirmada_at is None and ledger.disk_bytes_retenidos > 0


async def test_only_confirmed_absence_retires_claim(db, proxmox, perfil_capacidad, catedra, usuario_catedra, template):
    service, ledger = await materializado(db, proxmox, catedra, usuario_catedra, template)
    identity = await db.get(IdentidadInfraestructura, service.identidad_infraestructura_id)
    proxmox.delete_lxc(identity.nodo, identity.vmid)
    observation = await identities.observar(identity, pve=proxmox)
    assert observation.estado == 'ausente'
    identities.retirar(identity, observation)
    assert identity.ausencia_confirmada_at and identity.estado == 'retirada'


async def test_filtered_inventory_never_proves_global_absence(db, proxmox, perfil_capacidad, catedra, usuario_catedra, template, monkeypatch):
    service, ledger = await materializado(db, proxmox, catedra, usuario_catedra, template)
    identity = await db.get(IdentidadInfraestructura, service.identidad_infraestructura_id)
    monkeypatch.setattr(proxmox, 'get_cluster_resources', lambda *args: [])
    from app.services.infraestructura_io import InfraNoVerificable
    with pytest.raises(InfraNoVerificable):
        await identities.observar(identity, pve=proxmox)
    assert identity.ausencia_confirmada_at is None


async def test_orphan_volume_keeps_claim_even_without_guest_config(db, proxmox, perfil_capacidad, catedra, usuario_catedra, template):
    service, ledger = await materializado(db, proxmox, catedra, usuario_catedra, template)
    identity = await db.get(IdentidadInfraestructura, service.identidad_infraestructura_id)
    proxmox.delete_lxc(identity.nodo, identity.vmid)
    proxmox.contenidos_storage[('pve1', 'local-lvm')].append({'volid': f'local-lvm:vm-{identity.vmid}-disk-1', 'size': 1024})
    from app.services.infraestructura_io import InfraNoVerificable
    with pytest.raises(InfraNoVerificable):
        await identities.observar(identity, pve=proxmox)
    assert identity.ausencia_confirmada_at is None
