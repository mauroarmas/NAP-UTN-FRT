"""Manifiestos y evidencia sintéticos: nunca habilitan infraestructura real."""
from datetime import datetime, timezone
from uuid import uuid4


PRODUCTS = {'linux': 'iaas', 'postgresql': 'paas', 'bookstack': 'saas'}
CHECKS = ['image_digest', 'sanitized_image', 'repeatable_deployment', 'bootstrap_idempotence',
          'functional_access', 'student_network_access', 'persistence_after_restart', 'cross_instance_isolation']


def manifest(product='linux'):
    params = {'linux': ['display_name'], 'postgresql': ['display_name', 'database_name'],
              'bookstack': ['display_name', 'teacher_name', 'teacher_email', 'locale']}
    secrets = {'linux': ['guest_password'], 'postgresql': ['database_password'],
               'bookstack': ['teacher_password', 'database_password', 'app_key']}
    recipes = {'linux': 'linux-ubuntu-24.04-v1', 'postgresql': 'postgresql16-ubuntu-24.04-v1', 'bookstack': 'bookstack26-ubuntu-24.04-v1'}
    paths = {'linux': ['/'], 'postgresql': ['/var/lib/postgresql/16', '/etc/postgresql/16'],
             'bookstack': ['/var/lib/mysql', '/etc/mysql', '/var/www/bookstack/.env', '/var/www/bookstack/public/uploads', '/var/www/bookstack/storage/uploads', '/var/www/bookstack/themes']}
    components = {}
    packages = [{'name': 'base-files', 'version': '13ubuntu10.3', 'architecture': 'amd64'}]
    if product == 'postgresql':
        components['postgresql'] = {'version': '16.10'}
        packages.append({'name': 'postgresql-16', 'version': '16.10-1', 'architecture': 'amd64'})
    if product == 'bookstack':
        components = {'bookstack': {'version': '26.09.1', 'revision': 'c' * 40, 'source_sha256': 'd' * 64, 'composer_lock_sha256': 'e' * 64},
                      'php': {'version': '8.3.25'}, 'mariadb': {'version': '10.11.14'}}
        packages += [{'name': 'php8.3-fpm', 'version': '8.3.25-1', 'architecture': 'amd64'},
                     {'name': 'mariadb-server', 'version': '1:10.11.14-1', 'architecture': 'amd64'}]
    checks = CHECKS + ([] if product == 'linux' else ['unique_secrets']) + (['reader_permissions_and_revocation'] if product == 'bookstack' else [])
    return {'schema_version': '1.0', 'definition_key': product + '-test', 'definition_version': '1.0.0',
        'product': product, 'service_model': PRODUCTS[product], 'resource_type': 'lxc',
        'image': {'volume_id': f'local:vztmpl/{product}-test.tar.zst', 'sha256': 'a' * 64,
            'architecture': 'amd64', 'distribution': 'ubuntu', 'distribution_release': '24.04',
            'unprivileged': True, 'nesting': False, 'sanitized': True},
        'runtime': {'packages': packages, 'components': components},
        'preparation': {'recipe_id': recipes[product], 'recipe_revision': 'f' * 40, 'bundle_sha256': 'b' * 64,
            'bootstrap_id': product + '-v1', 'runner_protocol': 'nap-guest-runner/1'},
        'minimum_resources': {'vcpus': 1, 'ram_mb': 512, 'disk_gb': 4},
        'allowed_parameters': params[product], 'secret_metadata': {'generated_fields': secrets[product],
            'owner_reveal_fields': ['teacher_password'] if product == 'bookstack' else secrets[product],
            'guest_only_fields': ['database_password', 'app_key'] if product == 'bookstack' else [],
            'delivery': 'separate_authorized_endpoint'},
        'access': {'kind': {'linux': 'portal_console', 'postgresql': 'postgresql', 'bookstack': 'https'}[product],
            'port': {'linux': None, 'postgresql': 5432, 'bookstack': 443}[product],
            'endpoint_source': 'verified_infrastructure_profile', 'tls_required': True},
        'health': {'bootstrap_probe_id': {'linux': 'linux-ready-v1', 'postgresql': 'postgresql-write-read-v1', 'bookstack': 'bookstack-ready-v1'}[product],
            'recurring_probe_id': {'linux': 'linux-state-v1', 'postgresql': 'postgresql-authenticated-select-v1', 'bookstack': 'bookstack-status-v1'}[product],
            'timeout_seconds': 10, 'student_network_evidence_required': True},
        'persistent_paths': paths[product], 'network_profile_ids': ['test-network'],
        'validation': {'result': 'passed', 'validated_at': datetime.now(timezone.utc).isoformat(),
            'evidence_id': str(uuid4()), 'evidence_sha256': '0' * 64, 'cluster_uuid': str(uuid4()),
            'pve_versions': ['9.2.2'], 'instances_tested': 2, 'checks': checks}}


def definition_proof(row_id, value):
    proof = value['validation']
    return {'schema_version': 1, 'tipo': 'validacion_definicion', 'entorno': 'real',
        'operador_institucional': 'doble-aislado-de-pruebas', 'referencia_institucional': 'TEST-ONLY-009',
        'observado_at': proof['validated_at'].replace('+00:00', 'Z'),
        'resultado': {'definicion_id': str(row_id), 'definition_key': value['definition_key'],
            'definition_version': value['definition_version'], 'image_sha256': value['image']['sha256'],
            'recipe_sha256': value['preparation']['bundle_sha256'], 'cluster_uuid': proof['cluster_uuid'],
            'pve_versions': proof['pve_versions'], 'instancias': [str(uuid4()), str(uuid4())], 'checks': proof['checks']}}


async def link_capacity_definition(db, template, actor):
    """Fixture explícito de oferta validada, sin ejecutar ni publicar en PVE."""
    import hashlib
    from app.models.definicion_servicio import DefinicionServicio
    from app.models.evidencia import Evidencia
    from app.schemas.evidencia import canonical
    from app.schemas.definicion import digest
    from app.utils.clock import clock
    identity, reference = uuid4(), uuid4()
    value = manifest('linux')
    value['definition_key'] = 'linux-capacity-test'
    value['image']['volume_id'] = 'local:vztmpl/ubuntu-test.tar.zst'
    value['validation']['validated_at'] = clock.now().isoformat()
    proof = definition_proof(identity, value)
    encoded = canonical(proof)
    checksum = hashlib.sha256(encoded.encode()).hexdigest()
    db.add(Evidencia(id=reference, tipo='validacion_definicion', schema_version=1,
        documento_canonico=encoded, sha256=checksum, registrada_por=actor.id))
    await db.flush()
    value['validation'].update(evidence_id=str(reference), evidence_sha256=checksum)
    db.add(DefinicionServicio(id=identity, codigo=value['definition_key'], version='1.0.0', producto='linux',
        modelo_servicio='iaas', manifest=value, manifest_sha256=digest(value), estado='publicada',
        validada_por=actor.id, validada_at=clock.now(), evidencia_validacion=reference))
    template.definicion_version_id = identity
    template.os_template = value['image']['volume_id']
    await db.commit()
    return value
