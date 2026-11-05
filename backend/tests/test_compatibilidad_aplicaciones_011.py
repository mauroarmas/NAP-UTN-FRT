"""Regressions from real Redis/MariaDB requests; no simulated PVE acceptance."""
from copy import deepcopy

import pytest

from app.services.application_compatibility_service import incompatibility
from app.services.operacion_service import anexar_progreso_aplicacion, presentar
from tests.test_ingesta_consola_011 import console_job, batch
from tests.test_templates_aplicaciones_011 import (
    app_order, catalog_image, perfil_capacidad, red_aplicaciones_011, profile_entry,
)


@pytest.mark.parametrize('image', ['redis', 'redis:7', 'library/redis',
    'docker.io/library/redis@sha256:' + 'a' * 64, 'mariadb:11', 'mysql:latest',
    'docker.io/library/mysql:8', 'postgres:17'])
async def test_known_native_images_cannot_be_added_even_using_manual_entry(
    client, db, auth_admin, app_order, catalog_image, image,
):
    calls, _ = catalog_image
    response = await client.post('/templates/aplicaciones',
        headers=auth_admin | {'Idempotency-Key': 'native-' + str(len(image))},
        json={'nombre': 'Servicio de datos', 'imagen': image, 'puerto': 8080})
    assert response.status_code == 422
    assert response.json()['detail']['codigo'] == ('mariadb_version_no_admitida' if image=='mariadb:11' else 'aplicacion_no_compatible')
    assert ('11.4' if image=='mariadb:11' else 'adaptador') in response.json()['detail']['mensaje']
    assert not calls


def test_a_web_management_image_is_not_confused_with_its_database():
    assert incompatibility('redis')
    assert incompatibility('mysql')
    assert incompatibility('postgres')
    assert incompatibility('rediscommander/redis-commander') is None
    assert incompatibility('university/mariadb-admin') is None
    assert incompatibility('phpmyadmin') is None


async def test_existing_incompatible_offer_is_unavailable_with_an_explanation(db, app_order):
    from app.services.perfiles_service import anexar_disponibilidad
    from app.models.configuracion_despliegue import ConfiguracionDespliegue
    from app.schemas.configuracion_despliegue import digest_configuracion
    app = app_order
    document = deepcopy(app.config.documento)
    document['imagen']['repositorio'] = 'docker.io/library/mariadb'
    replacement = ConfiguracionDespliegue(**{key: getattr(app.config, key) for key in (
        'codigo', 'origen', 'modelo_servicio', 'perfil_id', 'perfil_revision', 'perfil_sha256', 'validaciones', 'creado_por')},
        revision=2, documento=document, sha256=digest_configuracion(document))
    db.add(replacement)
    await db.flush()
    app.template.configuracion_despliegue_id = replacement.id
    await db.flush()
    await anexar_disponibilidad(db, [app.template])
    assert app.template.oferta_disponible is False
    assert 'MariaDB' in app.template.motivo_no_disponible
    assert app.template.requiere_actualizar_perfil is False


async def test_historical_failed_access_is_read_from_captured_phase_without_rewriting_history(db, console_job):
    from app.services.consola_operacion_service import ingerir
    job = console_job
    response = batch(job, state='fallido')
    response['data']['error_codigo'] = 'DEPENDENCY_UNAVAILABLE'
    response['data']['fase'] = 'comprobacion'
    for item in response['data']['items']:
        item['fase'] = 'comprobacion'
    await ingerir(db, job.lease, request=job.request, response=response)
    job.operation.estado = 'fallida'
    job.operation.fase = 'finalizada'
    job.operation.error_codigo = 'DEPENDENCY_UNAVAILABLE'
    await db.commit()
    await anexar_progreso_aplicacion(db, [job.operation])
    result = presentar(job.operation)
    assert result['fase_aplicacion'] == 'comprobacion'
    assert result['error_codigo'] == 'acceso_aplicacion_no_disponible'
    assert job.operation.error_codigo == 'DEPENDENCY_UNAVAILABLE'
    assert job.operation.fase == 'finalizada'
    job.operation.contexto_seguro = {**job.operation.contexto_seguro, 'asignacion': {'configuracion': {
        'origen': 'imagen_docker', 'imagen': {'repositorio': 'docker.io/library/mariadb',
            'manifest_digest': 'sha256:' + 'a' * 64}}}}
    result = presentar(job.operation)
    assert result['error_codigo'] == 'acceso_aplicacion_no_disponible'
    assert result['reintento_disponible'] is False
    assert 'MariaDB' in result['motivo_compatibilidad']


async def test_search_explains_known_compatibility_without_claiming_unknown_images_are_tested(client, auth_admin, monkeypatch):
    from app.services import biblioteca_service
    async def search(*args, **kwargs):
        return {'count': 2, 'results': [{'repo_name': 'redis', 'is_official': True},
            {'repo_name': 'traefik/whoami'}]}
    monkeypatch.setattr(biblioteca_service, 'docker_hub_search', search)
    response = await client.get('/biblioteca/aplicaciones?q=redis', headers=auth_admin)
    assert response.status_code == 200
    native, web = response.json()['items']
    assert native['compatibilidad'] == 'no_compatible'
    assert 'adaptador' in native['motivo_no_disponible']
    assert web['compatibilidad'] == 'sin_comprobar'


async def test_retry_rejects_known_incompatibility_before_infrastructure_actions(client, db, auth_admin, app_order, proxmox):
    from app.models.pedido import EstadoPedido
    app = app_order
    document = deepcopy(app.config.documento)
    document['imagen']['repositorio'] = 'docker.io/library/redis'
    app.pedido.estado = EstadoPedido.ERROR
    app.pedido.configuracion_despliegue_id = app.config.id
    app.pedido.asignacion_snapshot = {'configuracion': document}
    await db.commit()
    response = await client.post(f'/pedidos/{app.pedido.id}/reintentar',
        headers=auth_admin | {'Idempotency-Key': 'retry-incompatible'}, json={})
    assert response.status_code == 422, response.text
    assert response.json()['detail']['codigo'] == 'aplicacion_no_compatible'
    assert not proxmox.creados
