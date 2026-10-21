from datetime import datetime, timezone, timedelta
from sqlalchemy import select
import pytest

from app.models.vigencia import VigenciaAutorizada
from app.models.compromiso_capacidad import CompromisoCapacidad
from app.utils.clock import clock, db_utc
from tests.capacity_helpers import perfil_capacidad, preparar_pedido, seleccion


@pytest.fixture(autouse=True)
def initial_lective_clock(monkeypatch):
    # Las sesiones se emiten con el mismo reloj que los escenarios futuros.
    monkeypatch.setattr(clock, 'now', lambda: datetime(2027, 1, 1, 12, tzinfo=timezone.utc))


def calendar(year=2027, revision=0):
    return {'revision_esperada': revision, 'periodos': [
        {'tipo': 'primer_cuatrimestre', 'desde': f'{year}-03-01', 'hasta': f'{year}-06-30'},
        {'tipo': 'segundo_cuatrimestre', 'desde': f'{year}-08-01', 'hasta': f'{year}-11-30'},
        {'tipo': 'anual', 'desde': f'{year}-03-01', 'hasta': f'{year}-11-30'}]}


async def put(client, headers, payload, *, year=2027, key='calendar'):
    return await client.put(f'/calendarios/{year}', json=payload, headers=headers | {'Idempotency-Key': key})


async def test_calendar_versioning_missing_modalities_and_roles(client, auth_admin, auth_catedra):
    assert (await client.get('/calendarios/2027', headers=auth_catedra)).status_code == 404
    assert (await put(client, auth_catedra, calendar())).status_code == 403
    payload = calendar()
    payload['periodos'] = payload['periodos'][:1]
    response = await put(client, auth_admin, payload)
    assert response.status_code == 201, response.text
    assert response.json()['revision'] == 1
    repeated = await put(client, auth_admin, payload)
    assert repeated.status_code == 201 and repeated.headers['idempotency-replayed'] == 'true'
    data = (await client.get('/calendarios/2027', headers=auth_catedra)).json()
    assert data['zona_horaria'] == 'America/Argentina/Tucuman'
    assert set(data['faltantes']) == {'segundo_cuatrimestre', 'anual'}
    assert (await put(client, auth_admin, calendar(), key='stale')).status_code == 409
    assert (await put(client, auth_admin, calendar(revision=1), key='new-revision')).status_code == 200
    assert (await put(client, auth_admin, calendar(2028), year=2028, key='next-year')).status_code == 201


async def test_overlapping_quarters_and_unknown_fields_rejected(client, auth_admin):
    payload = calendar()
    payload['periodos'][1]['desde'] = '2027-06-30'
    assert (await put(client, auth_admin, payload)).status_code == 422
    payload = calendar()
    payload['periodos'][0]['desde'] = '2027-06-01T00:00:00Z'
    assert (await put(client, auth_admin, payload)).status_code == 422
    payload = calendar()
    payload['periodos'].append(payload['periodos'][0])
    assert (await put(client, auth_admin, payload)).status_code == 422
    assert (await put(client, auth_admin, {**calendar(), 'zona_horaria': 'UTC'})).status_code == 422


async def test_future_approval_snapshots_survive_calendar_correction(client, db, perfil_capacidad, catedra, usuario_catedra, template, auth_admin, monkeypatch):
    now = datetime(2027, 1, 1, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(clock, 'now', lambda: now)
    assert (await put(client, auth_admin, calendar())).status_code == 201
    request = await preparar_pedido(db, catedra, usuario_catedra, template)
    payload = {**seleccion(template), 'vigencia': {'tipo': 'primer_cuatrimestre', 'anio_lectivo': 2027}}
    evaluation = await client.post(f'/pedidos/{request.id}/evaluacion', json=payload, headers=auth_admin)
    assert evaluation.status_code == 200, evaluation.text
    approval = await client.post(f'/pedidos/{request.id}/aprobar', json={**payload, 'capacidad_token': evaluation.json()['capacidad_token']}, headers=auth_admin | {'Idempotency-Key': 'approve-academic'})
    assert approval.status_code == 200, approval.text
    period = await db.scalar(select(VigenciaAutorizada))
    ledger = await db.scalar(select(CompromisoCapacidad))
    assert db_utc(period.inicio_at) == datetime(2027, 3, 1, 3, tzinfo=timezone.utc)
    assert db_utc(period.fin_exclusivo_at) == datetime(2027, 7, 1, 3, tzinfo=timezone.utc)
    assert db_utc(ledger.expira_at) == db_utc(period.inicio_at) + timedelta(hours=24)
    correction = calendar(revision=1)
    correction['periodos'][0]['hasta'] = '2027-06-15'
    assert (await put(client, auth_admin, correction, key='correct-calendar')).status_code == 200
    await db.refresh(period)
    assert period.hasta_local.isoformat() == '2027-06-30' and period.calendario_revision == 1
    projection = (await client.get(f'/pedidos/{request.id}', headers=auth_admin)).json()
    assert projection['vigencia_aprobada']['hasta'] == '2027-06-30'
    assert projection['vigencia_aprobada']['calendario_revision'] == 1
    assert not projection['despliegue_habilitado']
    denied = await client.post(f'/servicios/desplegar/{request.id}', json={}, headers=auth_admin | {'Idempotency-Key': 'too-early'})
    assert denied.status_code == 409 and denied.json()['detail']['codigo'] == 'inicio_futuro'


async def test_request_requires_available_period_and_closed_complete_payload(client, perfil_capacidad, catedra, template, auth_catedra):
    payload = {'template_id': template.id, 'modelo_servicio': 'iaas', 'vigencia': {'tipo': 'anual', 'anio_lectivo': 2027}}
    response = await client.post('/pedidos/', json=payload, headers=auth_catedra | {'Idempotency-Key': 'missing-calendar'})
    assert response.status_code == 422 and response.json()['detail']['codigo'] == 'calendario_no_configurado'
    for invalid in [
        {**payload, 'vigencia': {'tipo': 'anual'}},
        {**payload, 'vigencia': {'tipo': 'personalizado', 'desde': '2027-04-01'}},
        {**payload, 'vigencia': {'tipo': 'personalizado', 'desde': '2027-04-02', 'hasta': '2027-04-01'}},
        {**payload, 'parametros_extra': {'node': 'untrusted-node'}},
    ]:
        assert (await client.post('/pedidos/', json=invalid, headers=auth_catedra | {'Idempotency-Key': 'invalid-period'})).status_code == 422
