"""La asignación aprobada sobrevive a cambios posteriores del perfil."""
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.pedido import EstadoPedido
from app.models.servicio import Servicio
from app.models.compromiso_capacidad import CompromisoCapacidad
from app.models.operacion_infraestructura import OperacionInfraestructura
from app.worker import procesar_una
from tests.capacity_helpers import perfil_capacidad, seleccion, preparar_pedido, aprobar_http  # noqa:F401
from tests.test_operaciones_recuperacion import prepared_guest  # noqa:F401


@pytest.mark.parametrize('assignment,updated', [
    ((1,512,4), (4,4096,16)),
    ((2,1024,8), (8,8192,32)),
    ((1,512,4), (1,512,4)),
    ((4,2048,8), (1,512,4)),
], ids=['crece-perfil','cantidades-registradas','sin-cambio','encoge-perfil'])
async def test_despliegue_y_servicio_conservan_asignacion_aprobada(
    client, db, engine, proxmox, perfil_capacidad, prepared_guest, catedra, usuario_catedra, template, auth_admin,
    assignment, updated,
):
    pedido = await preparar_pedido(db, catedra, usuario_catedra, template)
    payload = seleccion(template)
    payload['asignacion'].update(dict(zip(['vcpus','ram_mb','disk_gb'],assignment)))
    result = await aprobar_http(client, pedido, template, auth_admin, payload=payload)
    assert result.status_code == 200, result.text
    template.default_vcpus, template.default_ram_mb, template.default_disk_gb = updated
    await db.commit()
    result = await client.post(f'/servicios/desplegar/{pedido.id}', json={}, headers=auth_admin | {'Idempotency-Key':'snapshot-dispatch'})
    assert result.status_code == 202, result.text
    await procesar_una(async_sessionmaker(engine, expire_on_commit=False), pve=proxmox)
    service = await db.scalar(select(Servicio))
    assert service is not None
    created = proxmox.creados[-1]
    assert (created['cores'], created['memory'], int(created['rootfs'].split(':')[-1])) == assignment
    assert (service.vcpus_asignados, service.ram_asignada_mb, service.disk_asignado_gb) == assignment
    assert service.disponibilidad_aplicacion == 'no_verificada' and service.url_acceso is None


async def test_si_el_envio_falla_retiene_asignacion_y_no_crea_servicio(
    client, db, engine, proxmox, perfil_capacidad, prepared_guest, catedra, usuario_catedra, template, auth_admin,
):
    pedido = await preparar_pedido(db, catedra, usuario_catedra, template)
    result = await aprobar_http(client, pedido, template, auth_admin)
    assert result.status_code == 200, result.text
    pedido_id = pedido.id
    await db.refresh(pedido); original = dict(pedido.asignacion_snapshot)
    result = await client.post(f'/servicios/desplegar/{pedido_id}', json={}, headers=auth_admin | {'Idempotency-Key':'uncertain-dispatch'})
    proxmox.fallar_create = RuntimeError('Proxmox no observable')
    await procesar_una(async_sessionmaker(engine, expire_on_commit=False), pve=proxmox)
    await db.refresh(pedido)
    operation = await db.get(OperacionInfraestructura, UUID(result.json()['operation_id']), populate_existing=True)
    ledger = await db.scalar(select(CompromisoCapacidad))
    assert operation.estado == 'incierta' and pedido.estado == EstadoPedido.EN_DESPLIEGUE
    assert await db.scalar(select(Servicio)) is None
    assert pedido.asignacion_snapshot == original
    assert ledger.vcpus_retenidos == original['vcpus'] and ledger.disk_bytes_retenidos == original['disk_gb']*1024**3


async def test_009_approved_assignment_is_immutable_before_dispatch(client, db, proxmox, perfil_capacidad, catedra, usuario_catedra, template, auth_admin):
    pedido = await preparar_pedido(db, catedra, usuario_catedra, template)
    payload = seleccion(template); payload['asignacion']['vcpus'] = 3
    approved = await aprobar_http(client, pedido, template, auth_admin, payload=payload)
    assert approved.status_code == 200, approved.text
    template.default_vcpus = 7; await db.commit()
    admitted = await client.post(f'/servicios/desplegar/{pedido.id}', headers=auth_admin | {'Idempotency-Key':'immutable-dispatch'}, json={})
    assert admitted.status_code == 202, admitted.text
    await db.refresh(pedido)
    assert pedido.asignacion_snapshot['vcpus'] == 3 and proxmox.creados == []
