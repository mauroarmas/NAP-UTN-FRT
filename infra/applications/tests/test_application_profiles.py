from copy import deepcopy
from hashlib import sha256
from uuid import uuid4

import pytest

from infra.applications.profiles.registry import ProfileRegistry
from infra.applications.job.protocol import JobError, canonical


@pytest.fixture
def profile_entry():
    definition = {'id': 'docker-ubuntu24', 'revision': 1, 'origen': 'imagen_docker',
        'base': {'os': 'ubuntu', 'version': '24.04', 'arquitectura': 'amd64',
                 'volumen_lxc': 'local:vztmpl/ubuntu-24.04.tar.zst', 'sha256': 'b'*64},
        'cluster_uuid': str(uuid4()), 'nodes': ['proxmox'],
        'platform': {'pve': '9.2.2', 'kernel': '7.0.2-6-pve', 'arquitectura': 'amd64'},
        'runtime': {'docker': '29.1.3', 'containerd': '2.2.1', 'runc': '1.3.4', 'storage_driver': 'overlayfs'},
        'features': ['nesting=1', 'keyctl=1'],
        'security': {'unprivileged': True, 'apparmor': 'enforce', 'seccomp': True},
        'minimum_resources': {'vcpus': 2, 'ram_mb': 1024, 'disk_gb': 8},
        'network_profile_id': 'campus-apps', 'policy_bundle_sha256': 'c'*64,
        'install_timeout_seconds': 2700, 'max_active_jobs_per_node': 2}
    return {'definition': definition, 'sha256': sha256(canonical(definition)).hexdigest(),
            'estado': 'pendiente_validacion', 'motivo_codigo': 'VALIDATION_REQUIRED', 'validacion': None}


def certify(entry):
    entry['estado'] = 'habilitado'; entry['motivo_codigo'] = None
    entry['validacion'] = {'tipo': 'proxmox_real', 'perfil_sha256': entry['sha256'],
        'cluster_uuid': entry['definition']['cluster_uuid'], 'platform': entry['definition']['platform'],
        'comprobaciones': ['aislamiento', 'runtime', 'persistencia', 'acceso', 'secretos']}
    return entry


def reference(entry):
    return {**{k: entry['definition'][k] for k in ('id', 'revision')}, 'sha256': entry['sha256']}


def test_empty_registry_and_pending_profile_do_not_enable(profile_entry):
    assert ProfileRegistry({}).capabilities() == []
    registry = ProfileRegistry({'docker-ubuntu24:1': profile_entry})
    assert registry.capabilities() == [{**reference(profile_entry), 'estado': 'pendiente_validacion',
                                        'motivo_codigo': 'VALIDATION_REQUIRED'}]
    with pytest.raises(JobError, match='PROFILE_UNAVAILABLE'):
        registry.require(reference(profile_entry))


def test_exact_certified_profile_and_defensive_copy(profile_entry):
    registry = ProfileRegistry({'docker-ubuntu24:1': certify(profile_entry)})
    result = registry.require(reference(profile_entry), cluster_uuid=profile_entry['definition']['cluster_uuid'],
        node='proxmox', platform=profile_entry['definition']['platform'])
    result['features'].append('unconfined')
    assert registry.require(reference(profile_entry))['features'] == ['nesting=1', 'keyctl=1']
    profile_entry['definition']['runtime']['docker'] = 'mutable'
    assert registry.require(reference(profile_entry))['runtime']['docker'] == '29.1.3'


@pytest.mark.parametrize('mutation', ['hash', 'fake', 'missing-proof', 'changed-platform', 'changed-base',
    'privileged', 'extra-feature', 'disabled-seccomp', 'extra-command', 'unbounded-jobs', 'budget', 'wrong-key'])
def test_invalid_or_uncertified_profile_is_never_enabled(profile_entry, mutation):
    entry = certify(deepcopy(profile_entry)); key = 'docker-ubuntu24:1'
    if mutation == 'hash': entry['sha256'] = '0'*64
    if mutation == 'fake': entry['validacion']['tipo'] = 'simulada'
    if mutation == 'missing-proof': entry['validacion']['comprobaciones'].remove('secretos')
    if mutation == 'changed-platform': entry['validacion']['platform']['pve'] = 'different'
    if mutation == 'changed-base': entry['definition']['base']['sha256'] = '0'*64
    if mutation == 'privileged': entry['definition']['security']['unprivileged'] = False
    if mutation == 'extra-feature': entry['definition']['features'].append('unconfined')
    if mutation == 'disabled-seccomp': entry['definition']['security']['seccomp'] = False
    if mutation == 'extra-command': entry['definition']['command'] = 'unsafe'
    if mutation == 'unbounded-jobs': entry['definition']['max_active_jobs_per_node'] = 3
    if mutation == 'budget': entry['definition']['install_timeout_seconds'] = 99999
    if mutation == 'wrong-key': key = 'docker-ubuntu24:2'
    with pytest.raises(JobError): ProfileRegistry({key: entry})


def test_actual_node_or_hash_mismatch_and_blocked_revision(profile_entry):
    registry = ProfileRegistry({'docker-ubuntu24:1': certify(profile_entry)})
    for kwargs in [{'node': 'another'}, {'cluster_uuid': str(uuid4())},
                   {'platform': {**profile_entry['definition']['platform'], 'kernel': 'changed'}}]:
        with pytest.raises(JobError, match='PROFILE_UNAVAILABLE'):
            registry.require(reference(profile_entry), **kwargs)
    wrong = reference(profile_entry); wrong['sha256'] = '0'*64
    with pytest.raises(JobError): registry.require(wrong)
    profile_entry.update(estado='bloqueado', motivo_codigo='PLATFORM_CHANGED')
    blocked = ProfileRegistry({'docker-ubuntu24:1': profile_entry})
    with pytest.raises(JobError): blocked.require(reference(profile_entry))
