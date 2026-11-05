"""Reserva de capacidad al aprobar: el corazón del modelo nuevo.

Sin reserva, el administrador puede aprobar tres pedidos seguidos viendo el
mismo saldo libre y sobrecomprometer el clúster sin cometer un solo error
individual: cada decisión sería correcta contra los números que vio. Estas
pruebas verifican que aprobar descuente en el acto.
"""

import pytest

from app.models.pedido import EstadoPedido
from app.models.servicio import EstadoServicio
from app.services import capacidad_service
from tests import factories
from tests.capacity_helpers import perfil_capacidad, GIB, seleccion, evaluar_http, aprobar_http, materializado
from app.config import get_settings

NODO = [
    {
        "node": "pve1",
        "status": "online",
        "cpu": 0.1,
        "maxcpu": 8,
        "maxmem": 16 * 1024**3,
        "maxdisk": 100 * 1024**3,
    }
]


@pytest.mark.parametrize('state', [EstadoPedido.EN_DESPLIEGUE, EstadoPedido.ERROR])
async def test_009_uncertain_commitment_is_retained_regardless_of_legacy_request_state(db, proxmox, perfil_capacidad, catedra, usuario_catedra, template, state):
    from app.models.compromiso_capacidad import CompromisoCapacidad
    pedido = await factories.crear_pedido(db, catedra.id, usuario_catedra.id, template.id, estado=state)
    db.add(CompromisoCapacidad(pedido_id=pedido.id, nodo='pve1', storage_id='local-lvm', storage_scope='node:pve1:local-lvm',
        vcpus_retenidos=2, ram_mb_retenida=1024, disk_bytes_retenidos=8 * GIB, estado='incierto'))
    await db.commit()
    value = await capacidad_service.panorama(db, pve=proxmox, destino={'nodo': 'pve1', 'storage': 'local-lvm'})
    assert value['comprometido']['vcpus'] == 2
    assert value['libre']['vcpus'] == 5  # 8 físicos - 1 anfitrión - 2 inciertos.
    assert value['libre']['disk_gb'] == 92


async def test_009_external_qemu_and_physical_free_are_counted_without_subtracting_disk_twice(db, proxmox, perfil_capacidad):
    proxmox.recursos = [{'type': 'qemu', 'vmid': 900, 'node': 'pve1', 'status': 'running'}]
    proxmox.configuraciones[('pve1', 900)] = {'cores': 2, 'sockets': 1, 'memory': 2048, 'scsi0': 'local-lvm:vm-900-disk-0,size=10G'}
    proxmox.storages[0]['avail'] = 90 * GIB
    proxmox.contenidos_storage[('pve1', 'local-lvm')] = [{'volid': 'local-lvm:vm-900-disk-0', 'size': 10 * GIB, 'content': 'images'}]
    value = await capacidad_service.panorama(db, pve=proxmox, destino={'nodo': 'pve1', 'storage': 'local-lvm'})
    assert value['externo']['vcpus'] == 2
    assert value['libre']['vcpus'] == 5
    assert value['libre']['disk_gb'] == 90


async def test_009_incomplete_storage_never_assumes_node_root_disk(db, proxmox, perfil_capacidad):
    from fastapi import HTTPException
    proxmox.storages[0].pop('avail')
    with pytest.raises(HTTPException) as failed:
        await capacidad_service.panorama(db, pve=proxmox, destino={'nodo': 'pve1', 'storage': 'local-lvm'})
    assert failed.value.status_code == 502


async def test_009_owned_resource_and_ledger_form_one_contribution(db, proxmox, perfil_capacidad, catedra, usuario_catedra, template):
    import hashlib
    import json
    from uuid import uuid4
    from app.models.compromiso_capacidad import CompromisoCapacidad
    from app.models.identidad_infraestructura import IdentidadInfraestructura
    from app.utils.secretos import configured_keyring
    from app.utils.clock import clock
    resource_uuid = uuid4()
    nonce = 'test-ownership-nonce'
    pedido = await factories.crear_pedido(db, catedra.id, usuario_catedra.id, template.id, estado=EstadoPedido.EN_DESPLIEGUE)
    identity = IdentidadInfraestructura(cluster_id=get_settings().infrastructure_profile['cluster_id'], vmid=100, nodo='pve1', pool_catedra=f'catedra-{catedra.id}',
        resource_uuid=resource_uuid, nonce_cifrado=configured_keyring().encrypt(nonce, context=f'infra:{resource_uuid}:nonce'),
        estado='materializada', ownership_verificada_at=clock.now())
    db.add(identity)
    await db.flush()
    service = await factories.crear_servicio(db, catedra.id, template.id, pedido_id=pedido.id, proxmox_vmid='100')
    service.identidad_infraestructura_id = identity.id
    db.add(CompromisoCapacidad(pedido_id=pedido.id, servicio_id=service.id, identidad_infraestructura_id=identity.id,
        nodo='pve1', storage_id='local-lvm', storage_scope='node:pve1:local-lvm', vcpus_retenidos=2,
        ram_mb_retenida=1024, disk_bytes_retenidos=10 * GIB, estado='materializado'))
    await db.commit()
    proxmox.recursos = [{'type': 'lxc', 'vmid': 100, 'node': 'pve1', 'status': 'running', 'pool': f'catedra-{catedra.id}'}]
    proxmox.configuraciones[('pve1', 100)] = {'cores': 2, 'memory': 1024, 'rootfs': 'local-lvm:vm-100-disk-0,size=10G',
        'description': json.dumps({'nap': {'resource_uuid': str(resource_uuid), 'nonce_sha256': hashlib.sha256(nonce.encode()).hexdigest(), 'pool': f'catedra-{catedra.id}'}})}
    proxmox.storages[0]['avail'] = 90 * GIB
    proxmox.contenidos_storage[('pve1', 'local-lvm')] = [{'volid': 'local-lvm:vm-100-disk-0', 'size': 10 * GIB, 'content': 'rootdir'}]
    value = await capacidad_service.panorama(db, pve=proxmox, destino={'nodo': 'pve1', 'storage': 'local-lvm'})
    assert value['comprometido']['vcpus'] == 2
    assert value['externo']['vcpus'] == 0
    assert value['libre']['disk_gb'] == 90


@pytest.fixture(autouse=True)
def cluster(proxmox, perfil_capacidad):
    return proxmox


async def _pedido_solicitado(db, catedra, usuario, template):
    return await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario.id,
        template_id=template.id,
        estado=EstadoPedido.SOLICITADO,
    )


async def test_aprobar_reserva_capacidad_antes_de_desplegar(
    client, db, catedra, usuario_catedra, template, auth_admin
):
    """El caso que motivó todo el rediseño."""
    pedido = await _pedido_solicitado(db, catedra, usuario_catedra, template)

    antes = await capacidad_service.panorama(db)
    assert antes["reservado"]["vcpus"] == 0

    r = await aprobar_http(client, pedido, template, auth_admin)
    assert r.status_code == 200, r.text

    despues = await capacidad_service.panorama(db)
    # Nada se desplegó todavía, pero la capacidad ya está comprometida.
    assert despues["desplegado"]["vcpus"] == antes["desplegado"]["vcpus"]
    assert despues["reservado"]["vcpus"] == template.default_vcpus
    assert despues["libre"]["vcpus"] == antes["libre"]["vcpus"] - template.default_vcpus


async def test_dos_aprobaciones_consecutivas_no_comparten_la_misma_capacidad(
    client, db, catedra, usuario_catedra, template, auth_admin
):
    """La segunda evaluación ya descuenta la primera aprobación."""
    uno = await _pedido_solicitado(db, catedra, usuario_catedra, template)
    dos = await _pedido_solicitado(db, catedra, usuario_catedra, template)

    _, ev_uno = await evaluar_http(client, uno, template, auth_admin)
    libre_inicial = ev_uno["libre_antes"]["vcpus"]

    await aprobar_http(client, uno, template, auth_admin)

    _, ev_dos = await evaluar_http(client, dos, template, auth_admin)
    libre_despues = ev_dos["libre_antes"]["vcpus"]

    assert libre_despues == libre_inicial - template.default_vcpus, (
        "la evaluación del segundo pedido debe descontar el primero, "
        "aunque su servicio todavía no exista"
    )


async def test_token_desactualizado_rechaza_la_aprobacion(
    client, db, catedra, usuario_catedra, template, auth_admin
):
    """Confirmar sobre números viejos no aprueba: pide reconfirmar."""
    uno = await _pedido_solicitado(db, catedra, usuario_catedra, template)
    dos = await _pedido_solicitado(db, catedra, usuario_catedra, template)

    # El admin abre el segundo pedido y se queda con ese token...
    body, ev = await evaluar_http(client, dos, template, auth_admin)
    token_viejo = ev["capacidad_token"]

    # ...pero en el medio se aprueba otro, y la capacidad cambia.
    await aprobar_http(client, uno, template, auth_admin)

    r = await client.post(
        f"/pedidos/{dos.id}/aprobar",
        json={**body, "capacidad_token": token_viejo},
        headers=auth_admin | {"Idempotency-Key":"legacy-capacity-decision"},
    )

    assert r.status_code == 409, r.text
    assert r.json()["detail"]["codigo"] == "evaluacion_desactualizada"
    await db.refresh(dos)
    assert dos.estado == EstadoPedido.SOLICITADO, "no debe aprobarse con datos viejos"


async def test_token_vigente_permite_aprobar(
    client, db, catedra, usuario_catedra, template, auth_admin
):
    pedido = await _pedido_solicitado(db, catedra, usuario_catedra, template)
    body, ev = await evaluar_http(client, pedido, template, auth_admin)

    r = await client.post(
        f"/pedidos/{pedido.id}/aprobar",
        json=body,
        headers=auth_admin | {"Idempotency-Key":"legacy-capacity-decision"},
    )

    assert r.status_code == 200, r.text


async def test_sobreasignar_sin_justificacion_no_aprueba(client, db, catedra, usuario_catedra, template, auth_admin, cluster):
    get_settings().infrastructure_profile['nodos']['pve1']['margen_vcpus'] = 7
    pedido = await _pedido_solicitado(db, catedra, usuario_catedra, template)
    payload = seleccion(template); payload['asignacion']['vcpus'] = 2
    r = await aprobar_http(client, pedido, template, auth_admin, payload=payload)
    assert r.status_code == 409, r.text
    assert r.json()['detail']['codigo'] == 'justificacion_capacidad_requerida'


async def test_sobreasignar_con_justificacion_dentro_del_limite_fisico(client, db, catedra, usuario_catedra, template, auth_admin, cluster):
    get_settings().infrastructure_profile['nodos']['pve1']['margen_vcpus'] = 7
    pedido = await _pedido_solicitado(db, catedra, usuario_catedra, template)
    payload = seleccion(template); payload['asignacion']['vcpus'] = 2
    r = await aprobar_http(client, pedido, template, auth_admin, payload=payload,
        justificacion_capacidad='Se apaga el laboratorio viejo esta semana')
    assert r.status_code == 200, r.text
    await db.refresh(pedido)
    assert pedido.justificacion_capacidad.startswith('Se apaga')


async def test_ram_en_riesgo_suma_los_pausados(
    client, db, catedra, template, auth_admin
):
    """Anticipa qué reactivaciones van a fallar, antes de que le fallen a alguien."""
    await factories.crear_servicio(
        db,
        catedra_id=catedra.id,
        template_id=template.id,
        proxmox_vmid="170",
        estado=EstadoServicio.PAUSED,
        ram_mb=2048,
    )

    estado = await capacidad_service.panorama(db)

    assert estado["ram_en_riesgo_mb"] == 2048


async def test_el_servicio_pausado_libera_computo_pero_no_disco(client, db, proxmox, catedra, usuario_catedra, template):
    await materializado(db, proxmox, catedra, usuario_catedra, template)
    estado = await capacidad_service.panorama(db)
    assert estado['desplegado']['vcpus'] == 0
    assert estado['desplegado']['ram_mb'] == 0
    assert estado['desplegado']['storage_gb'] == 10


async def test_solo_se_aprueban_pedidos_solicitados(
    client, db, catedra, usuario_catedra, template, auth_admin
):
    pedido = await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario_catedra.id,
        template_id=template.id,
        estado=EstadoPedido.APROBADO,
    )

    r = await client.post(f"/pedidos/{pedido.id}/aprobar", json=seleccion(template) | {"capacidad_token":"no-decide"}, headers=auth_admin | {"Idempotency-Key":"wrong-state"})

    assert r.status_code == 409, r.text


async def test_rechazar_exige_motivo_y_la_catedra_lo_ve(
    client, db, catedra, usuario_catedra, template, auth_admin, auth_catedra
):
    pedido = await _pedido_solicitado(db, catedra, usuario_catedra, template)

    pedido_id = pedido.id
    sin_motivo = await client.post(
        f"/pedidos/{pedido_id}/rechazar", json={"motivo": "  "}, headers=auth_admin | {"Idempotency-Key":"empty-reject"}
    )
    assert sin_motivo.status_code == 422

    con_motivo = await client.post(
        f"/pedidos/{pedido_id}/rechazar",
        json={"motivo": "El clúster está al límite este cuatrimestre"},
        headers=auth_admin | {"Idempotency-Key":"legacy-capacity-decision"},
    )
    assert con_motivo.status_code == 200, con_motivo.text

    visto = await client.get(f"/pedidos/{pedido_id}", headers=auth_catedra)
    assert "al límite" in visto.json()["motivo_rechazo"]
