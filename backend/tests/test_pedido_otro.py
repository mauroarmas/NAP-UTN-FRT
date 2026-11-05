from datetime import timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select, func

from app.models.pedido import Pedido, ModeloServicio
from app.models.recurso_template import RecursoTemplate, TipoRecurso
from app.models.compromiso_capacidad import CompromisoCapacidad
from app.models.servicio import Servicio
from app.utils.clock import clock
from tests import factories
from tests.capacity_helpers import perfil_capacidad, aprobar_http  # noqa: F401
from tests.service_helpers import link_capacity_definition


def solicitud(catedra, modelo='saas'):
    today = clock.now().astimezone(ZoneInfo('America/Argentina/Tucuman')).date()
    return {'modelo_servicio': modelo, 'template_id': None, 'catedra_id': catedra.id,
        'descripcion_requerimientos': 'Publicar apuntes y ejercicios para 40 estudiantes.',
        'parametros_extra': {'titulo': 'Apuntes de Bases de Datos', 'software_solicitado': 'Libro virtual'},
        'vigencia': {'tipo': 'personalizado', 'desde': today.isoformat(), 'hasta': (today + timedelta(days=30)).isoformat()}}


@pytest.mark.parametrize('modelo', ['paas', 'saas'])
async def test_otro_se_guarda_sin_crear_oferta_reservar_o_desplegar(client, db, catedra, auth_catedra, modelo):
    count = await db.scalar(select(func.count()).select_from(RecursoTemplate))
    headers = auth_catedra | {'Idempotency-Key': f'otro-{modelo}'}
    payload = solicitud(catedra, modelo)
    first = await client.post('/pedidos/', headers=headers, json=payload)
    assert first.status_code == 201, first.text
    data = first.json()
    assert data['template_id'] is None and data['definicion_version_id'] is None
    assert data['estado'] == 'solicitado'
    assert data['parametros_extra'] == payload['parametros_extra']
    assert data['descripcion_requerimientos'] == payload['descripcion_requerimientos']
    replay = await client.post('/pedidos/', headers=headers, json=payload)
    assert replay.json() == data
    assert replay.headers['idempotency-replayed'] == 'true'
    detail = await client.get(f'/pedidos/{data["id"]}', headers=auth_catedra)
    assert detail.json()['parametros_extra'] == payload['parametros_extra']
    assert await db.scalar(select(func.count()).select_from(RecursoTemplate)) == count
    assert await db.scalar(select(func.count()).select_from(CompromisoCapacidad)) == 0
    assert await db.scalar(select(func.count()).select_from(Servicio)) == 0


@pytest.mark.parametrize('change', [
    {'descripcion_requerimientos': '   '},
    {'parametros_extra': {'software_solicitado': '   '}},
    {'parametros_extra': {'software_solicitado': 'Libro', 'script': 'no permitido'}},
    {'modelo_servicio': 'iaas'},
])
async def test_otro_rechaza_datos_incompletos_y_parametros_libres(client, catedra, auth_catedra, change):
    response = await client.post('/pedidos/', headers=auth_catedra | {'Idempotency-Key': 'otro-invalido'},
        json=solicitud(catedra) | change)
    assert response.status_code == 422, response.text


async def test_admin_vincula_otro_con_oferta_publicada_sin_perder_justificacion(
    client, db, catedra, admin, auth_admin, auth_catedra, perfil_capacidad, proxmox
):
    payload = solicitud(catedra)
    created = await client.post('/pedidos/', headers=auth_catedra | {'Idempotency-Key': 'otro-libro'}, json=payload)
    assert created.status_code == 201, created.text
    pedido = await db.get(Pedido, created.json()['id'])
    template = await factories.crear_template(db, nombre='Libro de la cátedra', tipo=TipoRecurso.LXC,
        modelo_servicio=ModeloServicio.SAAS, vcpus=2, ram_mb=2048, disk_gb=8)
    await link_capacity_definition(db, template, admin, product='bookstack')
    proxmox.contenidos_storage[('pve1', 'local')].append({'volid': template.os_template, 'content': 'vztmpl'})
    approved = await aprobar_http(client, pedido, template, auth_admin)
    assert approved.status_code == 200, approved.text
    await db.refresh(pedido)
    assert pedido.template_id == template.id and pedido.definicion_version_id == template.definicion_version_id
    assert pedido.estado.value == 'aprobado'
    assert pedido.descripcion_requerimientos == payload['descripcion_requerimientos']
    assert pedido.parametros_extra == payload['parametros_extra']
    assert await db.scalar(select(func.count()).select_from(Servicio)) == 0


async def test_correccion_de_otro_conserva_la_necesidad_y_rechaza_modelo_incompatible(client, catedra, auth_admin, auth_catedra):
    payload = solicitud(catedra)
    created = await client.post('/pedidos/', headers=auth_catedra | {'Idempotency-Key': 'otro-corregir'}, json=payload)
    pedido_id = created.json()['id']
    adjustment = await client.post(f'/pedidos/{pedido_id}/solicitar-ajuste',
        headers=auth_admin | {'Idempotency-Key': 'otro-ajuste'}, json={'observaciones': 'Confirmar participantes'})
    assert adjustment.status_code == 200, adjustment.text
    invalid = await client.post(f'/pedidos/{pedido_id}/reenviar', headers=auth_admin | {'Idempotency-Key': 'otro-modelo-invalido'},
        json={'vigencia': payload['vigencia'], 'modelo_servicio': 'iaas'})
    assert invalid.status_code == 422, invalid.text
    updated = await client.post(f'/pedidos/{pedido_id}/reenviar', headers=auth_admin | {'Idempotency-Key': 'otro-corregido'},
        json={'vigencia': payload['vigencia'], 'descripcion_requerimientos': 'Publicar ejercicios para 50 estudiantes.'})
    assert updated.status_code == 200, updated.text
    assert updated.json()['template_id'] is None
    assert updated.json()['parametros_extra'] == payload['parametros_extra']
    assert updated.json()['descripcion_requerimientos'] == 'Publicar ejercicios para 50 estudiantes.'
