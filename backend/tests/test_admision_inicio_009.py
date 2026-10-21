import pytest
from app.models.operacion_infraestructura import OperacionInfraestructura
from sqlalchemy import select
from tests.capacity_helpers import perfil_capacidad, materializado


@pytest.mark.parametrize('route', ['start', 'reactivar'])
async def test_start_aliases_reserve_compute_once_without_external_io(client, db, proxmox, perfil_capacidad, catedra, usuario_catedra, template, auth_catedra, route):
    service, ledger = await materializado(db, proxmox, catedra, usuario_catedra, template)
    response = await client.post(f'/servicios/{service.id}/{route}', headers=auth_catedra | {'Idempotency-Key': 'same-start'})
    assert response.status_code == 202, response.text
    replay = await client.post(f'/servicios/{service.id}/start', headers=auth_catedra | {'Idempotency-Key': 'same-start'})
    assert replay.status_code == 202
    assert replay.json()['operation_id'] == response.json()['operation_id']
    await db.refresh(ledger)
    assert ledger.vcpus_retenidos == 2 and ledger.ram_mb_retenida == 1024
    assert ledger.disk_bytes_retenidos == 10 * 1024**3
    assert proxmox.iniciados == []
    assert len((await db.scalars(select(OperacionInfraestructura))).all()) == 1


async def test_future_renewal_does_not_grant_current_coverage(client, db, proxmox, perfil_capacidad, catedra, usuario_catedra, template, auth_catedra):
    service, ledger = await materializado(db, proxmox, catedra, usuario_catedra, template, future=True)
    response = await client.post(f'/servicios/{service.id}/start', headers=auth_catedra | {'Idempotency-Key': 'no-coverage'})
    assert response.status_code == 409, response.text
    assert response.json()['detail']['codigo'] == 'sin_cobertura_actual'
    await db.refresh(ledger)
    assert ledger.vcpus_retenidos == 0 and ledger.disk_bytes_retenidos > 0
    assert proxmox.iniciados == []


async def test_no_capacity_keeps_paused_service_and_retained_disk(client, db, proxmox, perfil_capacidad, catedra, usuario_catedra, template, auth_catedra):
    service, ledger = await materializado(db, proxmox, catedra, usuario_catedra, template)
    proxmox.recursos.append({'type': 'lxc', 'vmid': 900, 'node': 'pve1', 'status': 'running'})
    proxmox.configuraciones[('pve1', 900)] = {'cores': 6, 'memory': 1024}
    response = await client.post(f'/servicios/{service.id}/reactivar', headers=auth_catedra | {'Idempotency-Key': 'no-capacity'})
    assert response.status_code == 409
    assert response.json()['detail']['codigo'] == 'sin_capacidad'
    await db.refresh(service)
    await db.refresh(ledger)
    assert service.estado.value == 'paused' and ledger.vcpus_retenidos == 0
    assert ledger.disk_bytes_retenidos == 10 * 1024**3
