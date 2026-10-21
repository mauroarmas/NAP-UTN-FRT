import asyncio
from datetime import datetime, timezone, timedelta, date

from fastapi import HTTPException
import pytest
from sqlalchemy import select, func

from app.models.vigencia import VigenciaAutorizada
from app.models.pedido import Pedido
from app.models.usuario import Usuario
from app.models.servicio import EstadoServicio
from app.models.compromiso_capacidad import CompromisoCapacidad
from app.services import admision_service
from app.utils.clock import clock
from tests.capacity_helpers import perfil_capacidad, materializado


@pytest.fixture(autouse=True)
def initial_lective_clock(monkeypatch):
    monkeypatch.setattr(clock, 'now', lambda: datetime(2027, 3, 1, 12, tzinfo=timezone.utc))


def period(start, end):
    return {'tipo': 'personalizado', 'desde': start, 'hasta': end}


async def running(db, pve, catedra, user, template):
    service, ledger = await materializado(db, pve, catedra, user, template)
    original = await db.scalar(select(VigenciaAutorizada))
    original.hasta_local = date(2027, 3, 2)
    original.fin_exclusivo_at = datetime(2027, 3, 3, 3, tzinfo=timezone.utc)
    service.vence_at = datetime(2027, 3, 3, 3)
    service.estado = EstadoServicio.RUNNING
    ledger.vcpus_retenidos, ledger.ram_mb_retenida = 2, 1024
    pve.start_lxc('pve1', 100)
    await db.commit()
    return service, ledger, original


def selection(service, dates):
    return {'asignacion': {key: value for key, value in service.asignacion_snapshot.items()
        if key in {'template_id', 'definicion_version_id', 'vcpus', 'ram_mb', 'disk_gb'}},
        'destino': {'nodo': 'pve1', 'storage': 'local-lvm'}, 'vigencia': dates}


async def approve(client, request_id, payload, headers, key):
    evaluation = await client.post(f'/pedidos/{request_id}/evaluacion', json=payload, headers=headers)
    assert evaluation.status_code == 200, evaluation.text
    response = await client.post(f'/pedidos/{request_id}/aprobar', json={**payload, 'capacidad_token': evaluation.json()['capacidad_token']},
        headers=headers | {'Idempotency-Key': key})
    assert response.status_code == 200, response.text
    return response


async def test_pending_and_future_renewal_do_not_cover_gap_or_recreate(client, db, pg_sessions, proxmox, perfil_capacidad, catedra, usuario_catedra, template, auth_admin, auth_catedra, monkeypatch):
    now = datetime(2027, 3, 1, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(clock, 'now', lambda: now)
    service, ledger, original = await running(db, proxmox, catedra, usuario_catedra, template)
    service_id = service.id
    dates = period('2027-04-10', '2027-04-30')
    response = await client.post(f'/servicios/{service_id}/renovar', json={'vigencia': dates}, headers=auth_catedra | {'Idempotency-Key': 'renew-future'})
    assert response.status_code == 201, response.text
    request_id = response.json()['pedido_id']
    # Retirar el perfil no impide renovar la misma asignación histórica.
    template.activo = False
    await db.commit()
    await approve(client, request_id, selection(service, dates), auth_admin, 'approve-future')
    await db.refresh(service)
    assert service.estado == EstadoServicio.RUNNING and not proxmox.creados
    now = datetime(2027, 3, 5, 12, tzinfo=timezone.utc)
    from app.services.vencimiento_service import aplicar_vencimientos
    from app.worker import procesar_una
    await aplicar_vencimientos(db)
    await procesar_una(pg_sessions, pve=proxmox)
    await db.refresh(ledger)
    await db.refresh(service)
    assert service.estado == EstadoServicio.PAUSED
    assert ledger.vcpus_retenidos == ledger.ram_mb_retenida == 0 and ledger.disk_bytes_retenidos > 0
    from tests.auth_helpers import headers_para
    auth_catedra = await headers_para(db, usuario_catedra)
    denied = await client.post(f'/servicios/{service_id}/reactivar', headers=auth_catedra | {'Idempotency-Key': 'gap'})
    assert denied.status_code == 409 and denied.json()['detail']['codigo'] == 'sin_cobertura_actual'
    now = datetime(2027, 4, 10, 12, tzinfo=timezone.utc)
    auth_catedra = await headers_para(db, usuario_catedra)
    # Un recurso externo consume el nodo: la aprobación de fechas no reservó cómputo.
    proxmox.recursos.append({'type': 'qemu', 'vmid': 999, 'node': 'pve1', 'status': 'running'})
    proxmox.configuraciones[('pve1', 999)] = {'cores': 7, 'memory': 14000}
    denied = await client.post(f'/servicios/{service_id}/reactivar', headers=auth_catedra | {'Idempotency-Key': 'no-capacity'})
    assert denied.status_code == 409 and denied.json()['detail']['codigo'] == 'sin_capacidad'
    proxmox.recursos = [row for row in proxmox.recursos if row['vmid'] != 999]
    allowed = await client.post(f'/servicios/{service_id}/reactivar', headers=auth_catedra | {'Idempotency-Key': 'available'})
    assert allowed.status_code == 202, allowed.text
    await procesar_una(pg_sessions, pve=proxmox)
    await db.refresh(service)
    assert service.estado == EstadoServicio.RUNNING and service.proxmox_vmid == '100' and not proxmox.creados
    assert await db.scalar(select(func.count()).select_from(CompromisoCapacidad)) == 1


async def test_contiguous_approved_period_prevents_pause_but_pending_does_not(client, db, proxmox, perfil_capacidad, catedra, usuario_catedra, template, auth_admin, auth_catedra, monkeypatch):
    now = datetime(2027, 3, 1, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(clock, 'now', lambda: now)
    service, ledger, original = await running(db, proxmox, catedra, usuario_catedra, template)
    dates = period('2027-03-03', '2027-03-31')
    response = await client.post(f'/servicios/{service.id}/renovar', json={'vigencia': dates}, headers=auth_catedra | {'Idempotency-Key': 'contiguous'})
    assert response.status_code == 201, response.text
    await approve(client, response.json()['pedido_id'], selection(service, dates), auth_admin, 'approve-contiguous')
    now = datetime(2027, 3, 3, 3, tzinfo=timezone.utc)
    from app.services.vencimiento_service import aplicar_vencimientos
    await aplicar_vencimientos(db)
    await db.refresh(service)
    assert service.estado == EstadoServicio.RUNNING and not proxmox.detenidos
    assert await db.scalar(select(func.count()).select_from(VigenciaAutorizada)) == 2


async def test_concurrent_modifications_substitute_once_and_keep_history(client, db, pg_sessions, proxmox, perfil_capacidad, catedra, usuario_catedra, template, admin, auth_admin, monkeypatch):
    now = datetime(2027, 3, 1, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(clock, 'now', lambda: now)
    service, ledger, original = await running(db, proxmox, catedra, usuario_catedra, template)
    requests = []
    for end, key in [('2027-03-15', 'mod-one'), ('2027-03-20', 'mod-two')]:
        dates = period('2027-03-01', end)
        response = await client.post(f'/servicios/{service.id}/vigencias/{original.id}/modificaciones',
            json={'vigencia': dates, 'sustituye_vigencia_id': str(original.id), 'motivo': 'Corrección institucional'},
            headers=auth_admin | {'Idempotency-Key': key})
        assert response.status_code == 201, response.text
        payload = selection(service, dates)
        evaluated = await client.post(f"/pedidos/{response.json()['pedido_id']}/evaluacion", json=payload, headers=auth_admin)
        assert evaluated.status_code == 200, evaluated.text
        requests.append((response.json()['pedido_id'], {**payload, 'capacidad_token': evaluated.json()['capacidad_token']}))
    actor_id = admin.id
    barrier = asyncio.Barrier(2)
    async def decide(item, key):
        try:
            async with pg_sessions() as session, session.begin():
                actor = await session.get(Usuario, actor_id)
                await barrier.wait()
                await admision_service.aprobar(session, item[0], actor=actor, payload=item[1], clave=key, pve=proxmox)
            return 200
        except HTTPException as exc:
            return exc.status_code
    assert sorted(await asyncio.gather(*(decide(item, f'approve-{index}') for index, item in enumerate(requests)))) == [200, 409]
    assert await db.scalar(select(func.count()).select_from(VigenciaAutorizada)) == 2
    await db.refresh(original)
    assert original.hasta_local == date(2027, 3, 2)
    from app.services.vigencia_service import periodos_vigentes
    periods = await periodos_vigentes(db, service.id)
    assert len(periods) == 1 and periods[0].sustituye_id == original.id


async def test_pending_renewal_does_not_postpone_expiration(client, db, pg_sessions, proxmox, perfil_capacidad, catedra, usuario_catedra, template, auth_catedra, monkeypatch):
    now = datetime(2027, 3, 1, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(clock, 'now', lambda: now)
    service, ledger, original = await running(db, proxmox, catedra, usuario_catedra, template)
    response = await client.post(f'/servicios/{service.id}/renovar', json={'vigencia': period('2027-03-03', '2027-03-31')},
        headers=auth_catedra | {'Idempotency-Key': 'pending-only'})
    assert response.status_code == 201, response.text
    now = datetime(2027, 3, 3, 12, tzinfo=timezone.utc)
    from app.services.vencimiento_service import aplicar_vencimientos
    from app.worker import procesar_una
    await aplicar_vencimientos(db)
    await procesar_una(pg_sessions, pve=proxmox)
    await db.refresh(service)
    await db.refresh(ledger)
    assert service.estado == EstadoServicio.PAUSED and ledger.vcpus_retenidos == 0 and ledger.disk_bytes_retenidos > 0


async def test_approval_before_dispatch_cancels_obsolete_pause(client, db, pg_sessions, proxmox, perfil_capacidad, catedra, usuario_catedra, template, admin, auth_admin, auth_catedra, monkeypatch):
    now = datetime(2027, 3, 1, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(clock, 'now', lambda: now)
    service, ledger, original = await running(db, proxmox, catedra, usuario_catedra, template)
    dates = period('2027-03-03', '2027-03-31')
    response = await client.post(f'/servicios/{service.id}/renovar', json={'vigencia': dates}, headers=auth_catedra | {'Idempotency-Key': 'race-renewal'})
    assert response.status_code == 201
    request_id = response.json()['pedido_id']
    now = datetime(2027, 3, 3, 12, tzinfo=timezone.utc)
    from app.services.vencimiento_service import aplicar_vencimientos
    from app.worker import procesar_una
    await aplicar_vencimientos(db)
    from tests.auth_helpers import headers_para
    headers = await headers_para(db, admin)
    await approve(client, request_id, selection(service, dates), headers, 'race-approval')
    await procesar_una(pg_sessions, pve=proxmox)
    await db.refresh(service)
    assert service.estado == EstadoServicio.RUNNING and not proxmox.detenidos
