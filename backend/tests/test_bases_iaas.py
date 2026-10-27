"""Proxmox simulado: flujo real de dominio; no acredita ensayos de la VM."""
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import get_settings
from app.models.pedido import Pedido, EstadoPedido
from app.models.recurso_template import RecursoTemplate
from app.models.servicio import Servicio
from app.services import bases_iaas_service as bases, perfiles_service
from app.utils.clock import clock
from app.utils.secretos import configured_keyring
from tests.capacity_helpers import perfil_capacidad, aprobar_http  # noqa: F401


async def configure(monkeypatch, proxmox):
    settings = get_settings()
    slots = {str(uuid4()): {'host': f'linux{i}.example.edu', 'address': f'10.20.0.{i+20}',
        'mac_address': f'02:00:00:00:01:{i+20:02x}', 'products': ['linux']} for i in range(2)}
    monkeypatch.setattr(settings, 'iaas_network_profile_id', 'linux')
    monkeypatch.setattr(settings, 'network_profiles', {'linux': {'instances': slots,
        'nodes': ['pve1'], 'bridge': 'vmbr0', 'allowed_cidrs': ['10.20.0.0/24'],
        'client_cidrs': ['10.20.0.0/24'], 'ip_mode': 'static', 'static_cidr': '10.20.0.0/24', 'gateway': '10.20.0.1'}})
    proxmox.contenidos_storage[('pve1', 'local')] = [
        {'volid': 'local:vztmpl/ubuntu-24.04-standard_24.04-2_amd64.tar.zst', 'content': 'vztmpl'},
        {'volid': 'local:vztmpl/debian-13-standard_13.6-1_amd64.tar.zst', 'content': 'vztmpl'},
        {'volid': 'local:vztmpl/nap009-bookstack-1.0.0.tar.gz', 'content': 'vztmpl'}]


async def test_sincronizacion_idempotente_y_retiro_respetado(db, proxmox, perfil_capacidad, monkeypatch):
    await configure(monkeypatch, proxmox)
    assert await bases.sincronizar(db, pve=proxmox) == 2
    await db.commit()
    rows = [row for row in (await db.scalars(select(RecursoTemplate))).all() if bases.es_base(row)]
    assert sorted(row.nombre for row in rows) == ['Debian 13', 'Ubuntu 24.04']
    rows[0].activo = False
    await db.commit()
    await bases.sincronizar(db, pve=proxmox)
    await db.commit()
    await db.refresh(rows[0])
    assert not rows[0].activo
    assert len([row for row in (await db.scalars(select(RecursoTemplate))).all() if bases.es_base(row)]) == 2


@pytest.mark.parametrize('name', ['Ubuntu 24.04', 'Debian 13'])
async def test_iaas_solicitud_aprobacion_despliegue_acceso_sin_definicion(client, db, engine, admin, auth_admin,
        auth_catedra, proxmox, perfil_capacidad, monkeypatch, catedra, usuario_catedra, name):
    from app.worker import procesar_una
    from app.models.operacion_infraestructura import OperacionInfraestructura
    await configure(monkeypatch, proxmox)
    await bases.sincronizar(db, pve=proxmox)
    await db.commit()
    row = await db.scalar(select(RecursoTemplate).where(RecursoTemplate.nombre == name))
    await perfiles_service.anexar_disponibilidad(db, [row])
    assert row.oferta_disponible and row.tamanos_permitidos == ['small', 'medium']
    today = clock.now().date()
    response = await client.post('/pedidos/', headers=auth_catedra | {'Idempotency-Key': 'pedido-iaas'}, json={
        'template_id': row.id, 'modelo_servicio': 'iaas', 'catedra_id': catedra.id,
        'descripcion_requerimientos': 'Entorno para las prácticas de sistemas operativos.',
        'vigencia': {'tipo': 'personalizado', 'desde': today.isoformat(), 'hasta': (today+timedelta(days=7)).isoformat()}})
    assert response.status_code == 201, response.text
    pedido = await db.get(Pedido, response.json()['id'])
    approved = await aprobar_http(client, pedido, row, auth_admin, desplegar_inmediatamente=True)
    assert approved.status_code == 202, approved.text
    await db.commit()
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    for _ in range(8):
        await procesar_una(sessions, pve=proxmox)
    await db.refresh(pedido)
    assert pedido.estado == EstadoPedido.ACTIVO
    service = await db.get(Servicio, pedido.servicio_id)
    assert service.definicion_version_id is None
    assert service.disponibilidad_aplicacion == 'utilizable'
    assert service.asignacion_snapshot['origen'] == 'proxmox_iaas'
    assert service.acceso_metadata['username'] == 'root'
    values = configured_keyring().decrypt(service.credenciales_encrypted, context=f'servicio:{service.id}:secretos')
    assert len(values['guest_password']) >= 32
    assert values['guest_password'] not in str(service.asignacion_snapshot)
    op = await db.scalar(select(OperacionInfraestructura).where(OperacionInfraestructura.servicio_id == service.id))
    assert values['guest_password'] not in str(op.contexto_seguro)
    access = await client.post(f'/servicios/{service.id}/acceso/revelar', headers=auth_catedra, json={})
    assert access.status_code == 200, access.text
    assert access.json()['credenciales']['usuario'] == 'root'
    assert access.json()['credenciales']['password'] == values['guest_password']
    assert (await client.post('/templates/sincronizar-iaas', headers=auth_catedra)).status_code == 403
