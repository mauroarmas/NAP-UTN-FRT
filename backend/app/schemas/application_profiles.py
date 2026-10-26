"""Registro cerrado y sin dependencias para portal y paquete instalado del nodo.

El instalador copia este módulo al runner como profile_contract.py. El estado es
una decisión institucional explícita: este código no certifica ni habilita perfiles.
"""
from copy import deepcopy
from hashlib import sha256
import json
import re
from uuid import UUID


class ProfileError(ValueError):
    def __init__(self):
        super().__init__('PROFILE_UNAVAILABLE')


REASONS = {'VALIDATION_REQUIRED', 'PLATFORM_CHANGED', 'DEPENDENCY_UNAVAILABLE',
           'ISOLATION_FAILED', 'RESOURCE_LIMIT', 'ADMIN_BLOCKED'}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def _match(pattern, value):
    if type(value) is not str or not re.fullmatch(pattern, value): raise ProfileError()


def _keys(value, expected):
    if type(value) is not dict or set(value) != set(expected.split()): raise ProfileError()


def _positive(value, maximum):
    if type(value) is not int or not 1 <= value <= maximum: raise ProfileError()


def validate_definition(d):
    _keys(d, 'id revision origen base cluster_uuid nodes platform runtime features security minimum_resources network_profile_id policy_bundle_sha256 install_timeout_seconds max_active_jobs_per_node')
    _match(r'[a-z][a-z0-9-]{0,63}', d['id']); _positive(d['revision'], 2**31-1)
    _match(r'[a-z][a-z0-9-]{0,63}', d['network_profile_id'])
    _match(r'[a-f0-9]{64}', d['policy_bundle_sha256'])
    if type(d['cluster_uuid']) is not str or str(UUID(d['cluster_uuid'])) != d['cluster_uuid']: raise ProfileError()
    if type(d['nodes']) is not list or not 1 <= len(d['nodes']) <= 100 or len(set(d['nodes'])) != len(d['nodes']): raise ProfileError()
    for node in d['nodes']: _match(r'[A-Za-z0-9][A-Za-z0-9._-]{0,99}', node)
    base = d['base']; _keys(base, 'os version arquitectura volumen_lxc sha256')
    _match(r'[a-f0-9]{64}', base['sha256'])
    _match(r'[A-Za-z][A-Za-z0-9_-]*:vztmpl/[A-Za-z0-9][A-Za-z0-9_.-]*\.tar\.(?:zst|gz|xz)', base['volumen_lxc'])
    if base['arquitectura'] not in {'amd64', 'arm64'}: raise ProfileError()
    platform = d['platform']; _keys(platform, 'pve kernel arquitectura')
    for key in ('pve', 'kernel'): _match(r'[A-Za-z0-9][A-Za-z0-9.+:~_-]{0,99}', platform[key])
    if platform['arquitectura'] != base['arquitectura']: raise ProfileError()
    if (d['security'] != {'unprivileged': True, 'apparmor': 'enforce', 'seccomp': True}
            or type(d['security'].get('unprivileged')) is not bool or type(d['security'].get('seccomp')) is not bool): raise ProfileError()
    runtime = d['runtime']
    if d['origen'] == 'imagen_docker':
        if (base['os'], base['version']) != ('ubuntu', '24.04') or d['features'] != ['nesting=1', 'keyctl=1']: raise ProfileError()
        _keys(runtime, 'docker containerd runc storage_driver')
        if runtime['storage_driver'] not in {'overlay2', 'overlayfs'}: raise ProfileError()
    elif d['origen'] == 'community_scripts':
        if (base['os'], base['version']) != ('debian', '13') or d['features'] != []: raise ProfileError()
        _keys(runtime, 'systemd apt')
    else: raise ProfileError()
    for value in runtime.values(): _match(r'[A-Za-z0-9][A-Za-z0-9.+:~_-]{0,99}', value)
    minimum = d['minimum_resources']; _keys(minimum, 'vcpus ram_mb disk_gb')
    for k, maximum in [('vcpus', 2), ('ram_mb', 1024), ('disk_gb', 8)]: _positive(minimum[k], maximum)
    if d['origen'] == 'community_scripts' and minimum != {'vcpus': 2, 'ram_mb': 1024, 'disk_gb': 8}: raise ProfileError()
    if (type(d['install_timeout_seconds']) is not int or d['install_timeout_seconds'] != 2700
            or type(d['max_active_jobs_per_node']) is not int or d['max_active_jobs_per_node'] != 2): raise ProfileError()


class ProfileRegistry:
    def __init__(self, entries):
        try:
            if type(entries) is not dict or len(entries) > 200 or len(canonical(entries)) > 1048576: raise ProfileError()
            self._entries = deepcopy(entries)
            for key, entry in self._entries.items():
                _keys(entry, 'definition sha256 estado motivo_codigo validacion')
                d = entry['definition']; validate_definition(d)
                if key != f"{d['id']}:{d['revision']}" or sha256(canonical(d)).hexdigest() != entry['sha256']: raise ProfileError()
                if entry['estado'] not in {'pendiente_validacion', 'habilitado', 'bloqueado'}: raise ProfileError()
                if entry['estado'] == 'habilitado':
                    proof = entry['validacion']; _keys(proof, 'tipo perfil_sha256 cluster_uuid platform comprobaciones')
                    if (entry['motivo_codigo'] is not None or proof['tipo'] != 'proxmox_real'
                            or proof['perfil_sha256'] != entry['sha256'] or proof['cluster_uuid'] != d['cluster_uuid']
                            or proof['platform'] != d['platform'] or type(proof['comprobaciones']) is not list
                            or set(proof['comprobaciones']) != {'aislamiento', 'runtime', 'persistencia', 'acceso', 'secretos'}): raise ProfileError()
                elif entry['motivo_codigo'] not in REASONS: raise ProfileError()
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
            raise ProfileError() from None

    def capabilities(self):
        return [{'id': e['definition']['id'], 'revision': e['definition']['revision'],
                 'sha256': e['sha256'], 'estado': e['estado'], 'motivo_codigo': e['motivo_codigo']}
                for _, e in sorted(self._entries.items())]

    def require(self, reference, *, cluster_uuid=None, node=None, platform=None):
        try:
            _keys(reference, 'id revision sha256')
            _positive(reference['revision'], 2**31-1)
            _match(r'[a-z][a-z0-9-]{0,63}', reference['id'])
            _match(r'[a-f0-9]{64}', reference['sha256'])
            e = self._entries[f"{reference['id']}:{reference['revision']}"]; d = e['definition']
            if (e['estado'] != 'habilitado' or e['sha256'] != reference['sha256']
                    or cluster_uuid is not None and cluster_uuid != d['cluster_uuid']
                    or node is not None and node not in d['nodes']
                    or platform is not None and platform != d['platform']): raise ProfileError()
            return deepcopy(d)
        except (ValueError, TypeError, KeyError):
            raise ProfileError() from None
