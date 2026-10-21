from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

SCHEMA = json.loads((Path(__file__).resolve().parents[2] / 'specs/009-remediar-hallazgos-cierre/contracts/evidence.schema.json').read_text())
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())


def document(kind='validacion_definicion'):
    results = {
        'validacion_definicion': {
            'definicion_id': str(uuid4()), 'definition_key': 'postgresql16', 'definition_version': '1',
            'image_sha256': 'a' * 64, 'recipe_sha256': 'b' * 64, 'cluster_uuid': str(uuid4()),
            'pve_versions': ['8.4.1'], 'instancias': [str(uuid4()), str(uuid4())],
            'checks': ['image_digest', 'sanitized_image', 'repeatable_deployment', 'bootstrap_idempotence',
                       'functional_access', 'student_network_access', 'persistence_after_restart',
                       'cross_instance_isolation', 'unique_secrets'],
        },
        'acceso_instancia': {
            'servicio_id': 1, 'definicion_id': str(uuid4()), 'resource_uuid': str(uuid4()),
            'nonce_sha256': 'a' * 64, 'preparacion_id': str(uuid4()),
            'endpoint': 'https://libros.example.edu', 'equipo_origen': 'lab-01', 'red_origen': 'alumnos',
            'metodo': 'manual', 'pruebas': ['lectura_individual', 'persistencia'],
        },
        'revocacion_consola': {
            'cambio_consola_id': str(uuid4()), 'revision_esperada': 1, 'identidad_nativa': 'docente@pve',
            'scopes_resultantes': [], 'sesiones_previas_terminadas': True, 'url_directa_denegada': True,
            'otros_accesos_legitimos_comprobados': True,
        },
    }
    return {'schema_version': 1, 'tipo': kind, 'entorno': 'simulado',
            'operador_institucional': 'operador-prueba', 'referencia_institucional': 'TEST-009',
            'observado_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            'resultado': deepcopy(results[kind])}


@pytest.mark.parametrize('kind', ['validacion_definicion', 'acceso_instancia', 'revocacion_consola'])
def test_each_producer_has_a_closed_schema(kind):
    value = document(kind)
    VALIDATOR.validate(value)
    value['resultado']['password'] = 'prohibido'
    with pytest.raises(ValidationError):
        VALIDATOR.validate(value)


def test_malformed_uuid_wrong_type_and_unknown_fields_are_rejected():
    value = document()
    value['resultado']['definicion_id'] = 'otra-ruta-o-url'
    with pytest.raises(ValidationError):
        VALIDATOR.validate(value)
    value = document('revocacion_consola')
    value['resultado']['sesiones_previas_terminadas'] = False
    with pytest.raises(ValidationError):
        VALIDATOR.validate(value)
