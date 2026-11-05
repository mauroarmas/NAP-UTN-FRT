from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.identidad_infraestructura import IdentidadInfraestructura
from app.models.operacion_infraestructura import OperacionInfraestructura
from app.models.servicio import EstadoServicio
from app.services.estado_servicio_service import actualizar
from app.services.infraestructura_io import InfraNoVerificable
from app.utils.clock import clock
from app.worker import procesar_una
from tests.capacity_helpers import materializado, perfil_capacidad


async def test_observacion_repara_estado_y_habilita_admin(client, db, proxmox, perfil_capacidad,
        catedra, usuario_catedra, template, auth_admin, auth_catedra):
    service, ledger = await materializado(db, proxmox, catedra, usuario_catedra, template)
    identity = await db.get(IdentidadInfraestructura, service.identidad_infraestructura_id)
    ledger.estado, identity.estado = 'incierto', 'incierta'
    proxmox.estados[100] = 'running'
    await db.commit()
    response = await client.get(f'/servicios/{service.id}/status', headers=auth_admin)
    assert response.status_code == 200, response.text
    data = (await client.get(f'/servicios/{service.id}', headers=auth_admin)).json()
    assert data['estado'] == 'running' and data['estado_sincronizado']
    assert not data['regularizacion_pendiente']
    assert {'stop', 'restart', 'delete'} <= set(data['acciones_habilitadas'])
    assert 'delete' not in (await client.get(f'/servicios/{service.id}', headers=auth_catedra)).json()['acciones_habilitadas']
    await db.refresh(ledger)
    assert ledger.vcpus_retenidos == service.vcpus_asignados
    proxmox.estados[100] = 'stopped'
    await actualizar(db, service.id, pve=proxmox)
    assert ledger.vcpus_retenidos == 0 and ledger.disk_bytes_retenidos > 0


async def test_revision_no_bloquea_detener_o_borrar(client, db, proxmox, perfil_capacidad,
        catedra, usuario_catedra, template, auth_admin):
    service, ledger = await materializado(db, proxmox, catedra, usuario_catedra, template)
    service.nombre_snapshot = None
    ledger.estado, ledger.vcpus_retenidos = 'incierto', 2
    await db.commit()
    data = (await client.get(f'/servicios/{service.id}', headers=auth_admin)).json()
    assert set(data['acciones_habilitadas']) == {'stop', 'delete'}
    for action in ('stop',):
        response = await client.post(f'/servicios/{service.id}/{action}', json={},
            headers=auth_admin | {'Idempotency-Key': str(uuid4())})
        assert response.status_code == 202, response.text


async def test_no_reconcilia_identidad_ajena(db, proxmox, perfil_capacidad, catedra, usuario_catedra, template):
    service, ledger = await materializado(db, proxmox, catedra, usuario_catedra, template)
    ledger.estado = 'incierto'
    proxmox.configuraciones[('pve1', 100)]['description'] = '{}'
    with pytest.raises(InfraNoVerificable):
        await actualizar(db, service.id, pve=proxmox)
    assert ledger.estado == 'incierto'


async def test_observacion_respeta_operacion_abierta_y_recupera_stop_sin_reenviar(db, engine,
        proxmox, perfil_capacidad, catedra, usuario_catedra, template, admin):
    from app.services.operacion_service import admitir_orden
    service, ledger = await materializado(db, proxmox, catedra, usuario_catedra, template)
    service.estado = EstadoServicio.RUNNING
    ledger.vcpus_retenidos, ledger.estado = 2, 'incierto'
    await db.commit()
    await admitir_orden(db, service.id, tipo='detener', usuario=admin, clave=str(uuid4()))
    from sqlalchemy import select
    operation = await db.scalar(select(OperacionInfraestructura).where(OperacionInfraestructura.servicio_id == service.id))
    operation.fase, operation.estado = 'dispatch_started', 'incierta'
    operation.dispatch_started_at = clock.now() - timedelta(minutes=3)
    operation.deadline_at = clock.now() - timedelta(minutes=1)
    operation.contexto_seguro = {**operation.contexto_seguro, 'accion_externa': 'detener'}
    proxmox.estados[100] = 'stopped'
    await db.commit()
    await actualizar(db, service.id, pve=proxmox)
    assert ledger.estado == 'incierto' and service.estado == EstadoServicio.RUNNING
    await db.commit()
    await procesar_una(async_sessionmaker(engine, expire_on_commit=False), pve=proxmox)
    await db.refresh(operation)
    await db.refresh(service)
    assert operation.estado == 'confirmada'
    assert operation.contexto_seguro['resultado_por_observacion']
    assert service.estado == EstadoServicio.STOPPED
    assert not proxmox.detenidos


async def test_detener_ya_apagado_no_envia_post(db, engine, proxmox, perfil_capacidad,
        catedra, usuario_catedra, template, admin):
    from app.services.operacion_service import admitir_orden
    from sqlalchemy import select
    service, ledger = await materializado(db, proxmox, catedra, usuario_catedra, template)
    service.estado = EstadoServicio.RUNNING
    await db.commit()
    await admitir_orden(db, service.id, tipo='detener', usuario=admin, clave=str(uuid4()))
    await db.commit()
    await procesar_una(async_sessionmaker(engine, expire_on_commit=False), pve=proxmox)
    operation = await db.scalar(select(OperacionInfraestructura).where(OperacionInfraestructura.servicio_id == service.id))
    assert operation.estado == 'confirmada' and operation.contexto_seguro['sin_cambios']
    assert not proxmox.detenidos


async def test_estado_ajeno_o_timeout_no_libera_capacidad(db, proxmox, perfil_capacidad,
        catedra, usuario_catedra, template, monkeypatch):
    service, ledger = await materializado(db, proxmox, catedra, usuario_catedra, template)
    ledger.vcpus_retenidos, ledger.estado = 2, 'incierto'
    def timeout(*args):
        raise TimeoutError()
    monkeypatch.setattr(proxmox, 'get_lxc_status', timeout)
    with pytest.raises(InfraNoVerificable):
        await actualizar(db, service.id, pve=proxmox)
    assert ledger.vcpus_retenidos == 2 and ledger.estado == 'incierto'
