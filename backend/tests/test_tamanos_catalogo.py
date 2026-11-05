"""Contrato Small/Medium y conservación de la asignación autorizada."""
import pytest
from pydantic import ValidationError

from app.schemas.asignacion import AsignacionEfectiva
from app.schemas.ensayo import PerfilOferta
from app.schemas.template import TemplateCreate
from app.schemas.tamanos import TAMANOS, tamanos_compatibles
from tests.test_perfiles_definiciones_009 import published_linux, dates, profile  # noqa: F401
from tests.capacity_helpers import perfil_capacidad  # noqa: F401


async def test_tamanos_requieren_administrador(client, auth_admin, auth_catedra):
    assert (await client.get('/templates/tamanos')).status_code == 401
    assert (await client.get('/templates/tamanos', headers=auth_catedra)).status_code == 403
    response = await client.get('/templates/tamanos', headers=auth_admin)
    assert response.status_code == 200
    assert response.json() == [dict(id=name, nombre=name.title(), **resources) for name, resources in TAMANOS.items()]


@pytest.mark.parametrize('size', ['small', 'medium'])
async def test_aprobar_tamano_congela_recursos_y_no_reserva_al_publicar(
    client, db, auth_admin, auth_catedra, catedra, published_linux, size,
):
    from sqlalchemy import func, select
    from app.models.compromiso_capacidad import CompromisoCapacidad
    from app.models.pedido import Pedido

    identity, _ = published_linux
    body = {**profile(identity), 'tamano': 'small'}
    created = await client.post('/templates/', json=body, headers=auth_admin)
    assert created.status_code == 201, created.text
    template = created.json()
    assert template['tamanos_permitidos'] == ['small', 'medium']
    assert template['tamano_recomendado'] == 'small'
    assert await db.scalar(select(func.count()).select_from(CompromisoCapacidad)) == 0
    request = await client.post('/pedidos/', json={'template_id': template['id'], 'modelo_servicio': 'iaas', 'vigencia': dates()},
                                headers=auth_catedra | {'Idempotency-Key': 'request-size-' + size})
    assert request.status_code == 201, request.text
    selection = {'asignacion': {'template_id': template['id'], 'definicion_version_id': identity,
                               'tamano': size, **TAMANOS[size]}, 'vigencia': dates()}
    pid = request.json()['id']
    evaluated = await client.post(f'/pedidos/{pid}/evaluacion', json=selection, headers=auth_admin)
    assert evaluated.status_code == 200, evaluated.text
    wrong = {**selection, 'asignacion': {**selection['asignacion'], 'ram_mb': 9999}}
    assert (await client.post(f'/pedidos/{pid}/evaluacion', json=wrong, headers=auth_admin)).status_code == 422
    approved = await client.post(f'/pedidos/{pid}/aprobar', json={**selection, 'capacidad_token': evaluated.json()['capacidad_token']},
                                headers=auth_admin | {'Idempotency-Key': 'approve-size-' + size})
    assert approved.status_code == 200, approved.text
    before = approved.json()['asignacion_snapshot']
    assert before['tamano'] == size
    assert all(before[key] == value for key, value in TAMANOS[size].items())
    changed = await client.patch(f"/templates/{template['id']}", json={
        'tamano': 'medium', **{'default_' + key: value for key, value in TAMANOS['medium'].items()}}, headers=auth_admin)
    assert changed.status_code == 200, changed.text
    saved = await db.get(Pedido, pid, populate_existing=True)
    assert saved.asignacion_snapshot == before
    bad_patch = await client.patch(f"/templates/{template['id']}", json={'tamano': 'small', 'default_ram_mb': 9999}, headers=auth_admin)
    assert bad_patch.status_code == 422, bad_patch.text


@pytest.mark.parametrize('model', ['approval', 'offer', 'template'])
def test_tamano_no_permite_alterar_recursos(model):
    resources = TAMANOS['small']
    if model == 'approval':
        cls = AsignacionEfectiva
        payload = {'template_id': 1, **resources}
        wrong_key = 'ram_mb'
    else:
        cls = PerfilOferta if model == 'offer' else TemplateCreate
        payload = {'nombre': 'Prácticas', 'descripcion': '', **{'default_' + k: v for k, v in resources.items()}}
        if model == 'template':
            payload['definicion_version_id'] = '11111111-1111-4111-8111-111111111111'
        wrong_key = 'default_ram_mb'
    cls.model_validate({**payload, 'tamano': 'small'})
    with pytest.raises(ValidationError):
        cls.model_validate({**payload, 'tamano': 'large'})
    with pytest.raises(ValidationError):
        cls.model_validate({**payload, 'tamano': 'small', wrong_key: 9999})


def test_aplicacion_exigente_no_admite_tamanos_inferiores():
    assert tamanos_compatibles({'vcpus': 1, 'ram_mb': 1024, 'disk_gb': 4}) == ['medium']
    assert tamanos_compatibles({'vcpus': 1, 'ram_mb': 2048, 'disk_gb': 4}) == []
    assert tamanos_compatibles(None) == []
    assert tamanos_compatibles({'vcpus': 1, 'disk_gb': 4}) == []
