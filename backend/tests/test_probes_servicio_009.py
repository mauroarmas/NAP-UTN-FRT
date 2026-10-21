from uuid import UUID, uuid4

import pytest

from app.services.probes_servicio import confirmar
from app.services.infraestructura_io import InfraNoVerificable
from app.utils.clock import clock
from tests.test_guest_runner_client import request


def observation(product):
    value = request()
    suffix = UUID(value['resource_uuid']).hex
    value['parameters'] = {'display_name': 'Curso'}
    profile = {'allowed_cidrs': ['10.50.0.0/24'], 'instances': {
        value['resource_uuid']: {'host': 'curso.example.edu', 'address': '10.50.0.101'}}}
    result = {'ready': True, 'bootstrap_completed': True, 'addresses': ['10.50.0.101'],
        'host': 'curso.example.edu', 'address': '10.50.0.101'}
    if product == 'postgresql':
        result.update(port=5432, database='curso_' + suffix, username='curso_' + suffix, checks=['postgresql-select-v1'])
    else:
        value['parameters'].update(teacher_name='Ana', teacher_email='ana@example.edu', locale='es')
        result.update(port=443, username='ana@example.edu', endpoint='https://curso.example.edu', checks=['bookstack-status-v1'])
    response = {key: value[key] for key in ['protocol', 'operation_id', 'action', 'resource_uuid']}
    response.update(status='succeeded', phase='verified', observed_at=clock.now().isoformat(),
        identity_verified=True, result=result)
    return value, response, profile


@pytest.mark.parametrize('product', ['postgresql', 'bookstack'])
def test_authenticated_probe_projects_only_bound_institutional_endpoint(product):
    value, response, profile = observation(product)
    metadata = confirmar(response, value, product=product, profile=profile, service_id=1, preparation_id=uuid4())
    assert metadata['local_health'] and metadata['host'] == 'curso.example.edu'
    assert metadata['endpoint'].startswith('postgresql://' if product == 'postgresql' else 'https://')
    assert value['nonce'] not in str(metadata) and 'secrets' not in metadata


@pytest.mark.parametrize('product', ['postgresql', 'bookstack'])
@pytest.mark.parametrize('change', ['host', 'username', 'incomplete', 'foreign_operation'])
def test_partial_or_foreign_probe_never_creates_access(product, change):
    value, response, profile = observation(product)
    if change == 'host':
        response['result']['host'] = 'foreign.example.edu'
    elif change == 'username':
        response['result']['username'] = 'root'
    elif change == 'incomplete':
        response['result']['bootstrap_completed'] = False
    else:
        response['operation_id'] = str(uuid4())
    with pytest.raises(InfraNoVerificable):
        confirmar(response, value, product=product, profile=profile, service_id=1, preparation_id=uuid4())
