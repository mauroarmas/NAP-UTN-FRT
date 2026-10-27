from datetime import timedelta
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio

from app.config import get_settings
from app.utils.clock import clock

GIB = 1024 ** 3


@pytest_asyncio.fixture
async def perfil_capacidad(proxmox, monkeypatch, db, template, admin):
    from tests.service_helpers import link_capacity_definition
    definition = await link_capacity_definition(db, template, admin)
    profile = {'version': 1, 'cluster_id': definition['validation']['cluster_uuid'],
        'nodos': {'pve1': {'margen_vcpus': 1, 'margen_ram_mb': 512, 'storages': ['local-lvm']}},
        'almacenamientos': {'local-lvm': {'shared': False, 'margen_logico_bytes': 0, 'margen_fisico_bytes': 0}}}
    monkeypatch.setattr(get_settings(), 'infrastructure_profile', profile)
    proxmox.nodos = [{'node': 'pve1', 'status': 'online', 'maxcpu': 8, 'maxmem': 16 * GIB, 'mem': GIB}]
    proxmox.storages = [{'node': 'pve1', 'storage': 'local-lvm', 'content': 'rootdir,images',
                         'active': 1, 'enabled': 1, 'shared': 0, 'total': 100 * GIB, 'avail': 100 * GIB}]
    proxmox.contenidos_storage[('pve1', 'local-lvm')] = []
    proxmox.contenidos_storage[('pve1', 'local')] = [{'volid': 'local:vztmpl/ubuntu-test.tar.zst', 'content': 'vztmpl', 'size': GIB}]
    return profile


def seleccion(template, *, desde=None, hasta=None):
    today = clock.now().astimezone(ZoneInfo('America/Argentina/Tucuman')).date()
    return {'asignacion': {'template_id': template.id,
             **({'definicion_version_id': str(template.definicion_version_id)} if template.definicion_version_id else {}), 'vcpus': template.default_vcpus,
             'ram_mb': template.default_ram_mb, 'disk_gb': template.default_disk_gb},
        'destino': {'nodo': 'pve1', 'storage': 'local-lvm'},
        'vigencia': {'tipo': 'personalizado', 'desde': (desde or today).isoformat(),
                     'hasta': (hasta or today + timedelta(days=30)).isoformat()}}


async def evaluar_http(client, pedido, template, headers, *, payload=None):
    payload = payload or seleccion(template)
    result = await client.post(f'/pedidos/{pedido.id}/evaluacion', headers=headers, json=payload)
    assert result.status_code == 200, result.text
    return payload | {'capacidad_token':result.json()['capacidad_token']}, result.json()


async def aprobar_http(client, pedido, template, headers, *, clave=None, payload=None, **extra):
    body, _ = await evaluar_http(client, pedido, template, headers, payload=payload)
    return await client.post(f'/pedidos/{pedido.id}/aprobar', json=body | extra,
        headers=headers | {'Idempotency-Key':clave or f'aprobar-fixture:{pedido.id}'})


async def preparar_pedido(db, catedra, usuario, template):
    from tests import factories
    from app.models.pedido import EstadoPedido
    from sqlalchemy import inspect
    category_id, user_id, template_id = [inspect(row).identity[0] for row in [catedra, usuario, template]]
    await db.refresh(template)
    template.os_template = 'local:vztmpl/ubuntu-test.tar.zst'
    await db.commit()
    return await factories.crear_pedido(db, category_id, user_id, template_id, estado=EstadoPedido.SOLICITADO)


async def materializado(db, pve, catedra, usuario, template, *, vmid=100, vcpus=2, future=False):
    from uuid import uuid4
    import hashlib
    import json
    from app.models.identidad_infraestructura import IdentidadInfraestructura
    from app.models.compromiso_capacidad import CompromisoCapacidad
    from app.models.vigencia import VigenciaAutorizada
    from app.models.servicio import EstadoServicio
    from app.models.pedido import EstadoPedido
    from app.utils.secretos import configured_keyring
    from app.services.vigencia_service import resolver_fechas
    from tests import factories
    pedido = await factories.crear_pedido(db, catedra.id, usuario.id, template.id, estado=EstadoPedido.ACTIVO)
    resource_uuid, nonce = uuid4(), 'test-' + str(uuid4())
    identity = IdentidadInfraestructura(cluster_id=get_settings().infrastructure_profile['cluster_id'], vmid=vmid, nodo='pve1', pool_catedra=f'catedra-{catedra.id}',
        resource_uuid=resource_uuid, nonce_cifrado=configured_keyring().encrypt(nonce, context=f'infra:{resource_uuid}:nonce'),
        estado='materializada', ownership_verificada_at=clock.now())
    db.add(identity)
    await db.flush()
    service = await factories.crear_servicio(db, catedra.id, template.id, pedido_id=pedido.id,
        proxmox_vmid=str(vmid), estado=EstadoServicio.PAUSED, vcpus=vcpus, ram_mb=1024, disk_gb=10)
    service.identidad_infraestructura_id = identity.id
    identity.servicio_id = service.id
    service.modelo_servicio = template.modelo_servicio.value
    service.nombre_snapshot = template.nombre
    service.asignacion_snapshot = {'template_id': template.id, 'vcpus': vcpus, 'ram_mb': 1024, 'disk_gb': 10}
    service.disponibilidad_aplicacion = 'utilizable'
    ledger = CompromisoCapacidad(pedido_id=pedido.id, servicio_id=service.id, identidad_infraestructura_id=identity.id,
        nodo='pve1', storage_id='local-lvm', storage_scope='node:pve1:local-lvm', vcpus_retenidos=0,
        ram_mb_retenida=0, disk_bytes_retenidos=10 * GIB, estado='materializado')
    db.add(ledger)
    today = clock.now().astimezone(ZoneInfo('America/Argentina/Tucuman')).date()
    period = resolver_fechas(today + timedelta(days=7) if future else today, today + timedelta(days=30), 'America/Argentina/Tucuman')
    db.add(VigenciaAutorizada(pedido_id=pedido.id, revision_decision=1, servicio_id=service.id, modalidad='personalizado',
        desde_local=period.desde, hasta_local=period.hasta, zona_horaria=period.zona_horaria,
        inicio_at=period.inicio_at, fin_exclusivo_at=period.fin_exclusivo_at, aprobado_at=clock.now()))
    await db.commit()
    pve.recursos.append({'type': 'lxc', 'vmid': vmid, 'node': 'pve1', 'status': 'stopped', 'pool': f'catedra-{catedra.id}'})
    pve.configuraciones[('pve1', vmid)] = {'cores': vcpus, 'memory': 1024, 'unprivileged': 1, 'rootfs': f'local-lvm:vm-{vmid}-disk-0,size=10G',
        'description': json.dumps({'nap': {'resource_uuid': str(resource_uuid), 'nonce_sha256': hashlib.sha256(nonce.encode()).hexdigest(), 'pool': f'catedra-{catedra.id}'}})}
    pve.contenidos_storage[('pve1', 'local-lvm')].append({'volid': f'local-lvm:vm-{vmid}-disk-0', 'size': 10 * GIB, 'content': 'rootdir'})
    pve.storages[0]['avail'] -= 10 * GIB
    return service, ledger
