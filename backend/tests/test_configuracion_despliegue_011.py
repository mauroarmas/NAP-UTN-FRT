"""Contrato interno nuevo: datos cerrados, ninguna ejecución o credencial pública."""

from copy import deepcopy
import json

import pytest
from fastapi import HTTPException

from app.schemas.configuracion_despliegue import (
    validar_documento, parse_documento, digest_configuracion, adapter, RESERVED, FORBIDDEN_TARGETS,
)

from infra.applications.job.configuration import validate_configuration
from infra.applications.job.protocol import JobError, parse_request, fingerprint
from pathlib import Path
from uuid import uuid4


def test_docker_contract_canonical_hash_and_copy_are_stable(documento_docker):
    result = validar_documento(documento_docker)
    first = digest_configuracion(result)
    reordered = dict(reversed(list(documento_docker.items())))
    assert first == digest_configuracion(reordered) and len(first) == 64
    result['variables']['COURSE_NAME'] = 'Otro'
    assert documento_docker['variables']['COURSE_NAME'] == 'Introducción'
    assert digest_configuracion(result) != first


@pytest.mark.parametrize('key,value', [('command', 'sh -c unsafe'), ('privileged', True),
    ('devices', ['/dev/kvm']), ('network_mode', 'host'), ('definicion_version_id', 'legacy')])
def test_no_commands_flags_or_legacy_document_mixing(documento_docker, key, value):
    documento_docker[key] = value
    with pytest.raises(Exception) as caught: validar_documento(documento_docker)
    assert caught.value.status_code == 422


@pytest.mark.parametrize('name', ['PATH', 'BASH_ENV', 'LD_PRELOAD', 'PYTHONPATH', 'FUNCTIONS_FILE_PATH',
    'COMMUNITY_SCRIPTS_CORE_URL', 'DIAGNOSTICS', 'TELEMETRY_URL', 'DEV_MODE_TRACE', 'SSH_ROOT'])
def test_reserved_environment_cannot_change_runner_policy(documento_docker, name):
    documento_docker['variables'][name] = 'untrusted'
    with pytest.raises(Exception) as caught: validar_documento(documento_docker)
    assert caught.value.status_code == 422


@pytest.mark.parametrize('path', ['/', '/proc/cpuinfo', '/sys/kernel', '/dev/sda', '/run/docker.sock',
    '/var/run/docker.sock', '/etc/pve', '/var/lib/lxc', '/data/../root', '/data//cache', 'relative'])
def test_mount_targets_cannot_escape_application_policy(documento_docker, path):
    documento_docker['persistencia'] = [path]
    with pytest.raises(Exception) as caught: validar_documento(documento_docker)
    assert caught.value.status_code == 422


def test_credentials_never_become_public_config_or_errors(documento_docker):
    value = 'do-not-copy-sensitive-011'
    documento_docker['secretos'][0]['valor'] = value
    with pytest.raises(Exception) as caught: validar_documento(documento_docker)
    assert value not in str(caught.value.detail)
    del documento_docker['secretos'][0]['valor']
    documento_docker['imagen']['repositorio'] = 'user:' + value + '@registry.example.edu/app'
    with pytest.raises(Exception) as caught: validar_documento(documento_docker)
    assert value not in str(caught.value.detail)


@pytest.mark.parametrize('change', ['variables', 'paths', 'memory', 'boolean', 'nul', 'size', 'collision'])
def test_limits_and_no_type_coercion(documento_docker, change):
    if change == 'variables': documento_docker['variables'] = {f'KEY_{i}': 'v' for i in range(21)}
    if change == 'paths': documento_docker['persistencia'] = [f'/data/{i}' for i in range(9)]
    if change == 'memory': documento_docker['minimum_resources']['ram_mb'] = 2048
    if change == 'boolean': documento_docker['minimum_resources']['vcpus'] = True
    if change == 'nul': documento_docker['variables']['COURSE_NAME'] = 'a\x00b'
    if change == 'size': documento_docker['variables'] = {f'KEY_{i}': 'é' * 4096 for i in range(20)}
    if change == 'collision': documento_docker['variables']['APP_PASSWORD'] = 'cannot-shadow-secret'
    with pytest.raises(Exception) as caught: validar_documento(documento_docker)
    assert caught.value.status_code == 422


def test_probe_cannot_be_an_external_or_sensitive_url(documento_docker):
    for value in ['https://localhost/admin', '//other.edu/check', '/health?password=private']:
        documento_docker['access']['probe']['path'] = value
        with pytest.raises(Exception) as caught: validar_documento(documento_docker)
        assert caught.value.status_code == 422


def test_duplicate_keys_and_floats_are_rejected(documento_docker):
    raw = json.dumps(documento_docker).encode()
    assert parse_documento(raw)['origen'] == 'imagen_docker'
    duplicate = raw[:-1] + b',"origen":"community_scripts"}'
    for invalid in [duplicate, raw.replace(b'1024', b'1024.0'), b'{"value":NaN}']:
        with pytest.raises(Exception) as caught: parse_documento(invalid)
        assert caught.value.status_code == 422


@pytest.fixture
def documento_community(documento_docker):
    value = deepcopy(documento_docker)
    value.pop('imagen')
    value.update(origen='community_scripts', modelo_servicio='paas')
    value['base'].update(os='debian', version='13')
    value['perfil']['id'] = 'community-mariadb'
    value['access'] = {'tipo': 'tcp', 'puerto': 3306, 'politica': 'mariadb-tls',
                       'probe': {'tipo': 'mariadb_select_1', 'timeout_segundos': 5}}
    value['community'] = {'slug': 'mariadb', 'identidad_externa': 'ct/mariadb.sh',
        'instalador': 'install/mariadb-install.sh', 'proxmoxve_commit': 'e'*40, 'core_commit': 'f'*40,
        **{key: 'a'*64 for key in ('instalador_sha256', 'core_sha256', 'harness_sha256',
              'manifiesto_sha256', 'politica_sha256', 'dependencias_sha256')},
        'respuestas': {'phpmyadmin': 'no'}, 'postconfiguracion': 'mariadb-tls',
        'depuracion': 'salida-cerrada-v1'}
    return value


def test_schema_export_matches_models_and_node_policy():
    path = Path(__file__).resolve().parents[2] / 'infra/applications/schemas/nap-deployment-1.json'
    published = json.loads(path.read_text())
    expected = adapter.json_schema()
    expected['x-nap-policy'] = {'reserved_variables': sorted(RESERVED), 'forbidden_targets': list(FORBIDDEN_TARGETS)}
    expected['$schema'] = 'https://json-schema.org/draft/2020-12/schema'
    assert published == expected


@pytest.mark.parametrize('fixture_name', ['documento_docker', 'documento_community'])
def test_node_and_backend_validate_same_approved_configuration(request, fixture_name):
    value = request.getfixturevalue(fixture_name)
    normalized = validar_documento(value)
    assert validate_configuration(normalized) == normalized
    invalid = []
    for mutation in [('extra', 'command'), ('reserved', 'DOCKER_HOST'), ('target', '/etc/nap'),
                     ('target', '/data/../root'), ('resource', True), ('architecture', 'arm64'),
                     ('float', 1024.0), ('collision', 'APP_PASSWORD')]:
        changed = deepcopy(value)
        kind, item = mutation
        if kind == 'extra': changed[item] = 'unsafe'
        if kind == 'reserved': changed['variables'][item] = 'unsafe'
        if kind == 'target': changed['persistencia'] = [item]
        if kind == 'resource': changed['minimum_resources']['vcpus'] = item
        if kind == 'architecture':
            if 'imagen' in changed: changed['imagen']['arquitectura'] = item
            else: changed['community']['respuestas']['unapproved'] = item
        if kind == 'float': changed['minimum_resources']['ram_mb'] = item
        if kind == 'collision': changed['variables'][item] = 'unsafe'
        invalid.append(changed)
    for changed in invalid:
        with pytest.raises(HTTPException): validar_documento(changed)
        with pytest.raises(JobError): validate_configuration(changed)


def test_start_binds_config_hash_references_and_private_values(documento_docker):
    configuration = validar_documento(documento_docker)
    request = {'protocol': 'nap-application-job/1', 'action': 'start',
        **{key: str(uuid4()) for key in ('operation_id', 'operacion_raiz_id', 'intento_id',
            'execution_id', 'cluster_uuid', 'resource_uuid')},
        'lease_generation': 1, 'node': 'proxmox', 'vmid': 900011, 'pool': 'nap-apps',
        'nonce': 'f'*64, 'configuracion_sha256': digest_configuracion(configuration),
        'perfil': configuration['perfil'], 'configuracion': configuration,
        'secretos': {'APP_PASSWORD': 'fixture-not-real'},
        'secreto_referencias': [{'id': str(uuid4()), 'nombre': 'APP_PASSWORD', 'revision': 1}]}
    wire = lambda v: json.dumps(v).encode()
    assert parse_request(wire(request)) == request
    first = fingerprint(request)
    request['secretos']['APP_PASSWORD'] = 'fixture-retry-value'
    assert fingerprint(request) == first
    for key in ['configuracion_sha256', 'secretos', 'secreto_referencias', 'perfil']:
        invalid = deepcopy(request)
        if key == 'configuracion_sha256': invalid[key] = '0'*64
        if key == 'secretos': invalid[key]['EXTRA'] = 'should-not-leak'
        if key == 'secreto_referencias': invalid[key][0]['nombre'] = 'EXTRA'
        if key == 'perfil': invalid[key]['revision'] = 2
        with pytest.raises(JobError) as caught: parse_request(wire(invalid))
        assert 'should-not-leak' not in str(caught.value)


def test_community_does_not_accept_host_wrapper_or_mutable_sources(documento_community):
    for field, bad in [('instalador', 'ct/mariadb.sh'), ('instalador', 'https://bad/guest.sh'),
                       ('core_commit', 'main'), ('postconfiguracion', 'shell')]:
        value = deepcopy(documento_community); value['community'][field] = bad
        with pytest.raises(HTTPException): validar_documento(value)
    documento_community['community']['respuestas']['phpmyadmin'] = 'yes'
    with pytest.raises(HTTPException): validar_documento(documento_community)
