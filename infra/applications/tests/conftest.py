"""Shared pure application-runner fixtures; no node/registry connections."""
from hashlib import sha256
from uuid import uuid4

import pytest

from infra.applications.job.protocol import canonical


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

