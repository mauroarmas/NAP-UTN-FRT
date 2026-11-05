from copy import deepcopy
import json

import pytest

from infra.runner.node_executor import ApplicationNodeExecutor
from infra.applications.job.protocol import JobError, public_identity
from infra.applications.tests.test_job_supervisor import rig


@pytest.fixture
def native(rig):
    identity = public_identity(rig.request); identity.pop('lease_generation')
    profile = rig.supervisor.profiles.require(identity['perfil'])
    values = {'resource': {'vmid': identity['vmid'], 'type': 'lxc', 'node': identity['node'], 'pool': identity['pool']},
        'config': {'description': json.dumps({'nap': {'cluster_uuid': identity['cluster_uuid'],
            'resource_uuid': identity['resource_uuid'], 'nonce_sha256': identity['nonce_sha256'], 'pool': identity['pool'],
            'definition_sha256': identity['configuracion_sha256'], 'bundle_sha256': profile['policy_bundle_sha256']}}),
            'unprivileged': 1, 'cores': 2, 'memory': 1024, 'rootfs': 'local-lvm:vm-900011-disk-0,size=8G'},
        'status': 'stopped', 'calls': []}
    def run(argv, **kwargs):
        values['calls'].append(argv)
        if argv[0] == '/usr/sbin/pct':
            assert argv == ['/usr/sbin/pct', 'set', str(identity['vmid']), '--features', 'nesting=1,keyctl=1']
            values['config']['features'] = 'nesting=1,keyctl=1'
            return b''
        if '/cluster/resources' in argv: result = [values['resource']]
        elif any(v.endswith('/config') for v in argv): result = values['config']
        elif any(v.endswith('/status/current') for v in argv): result = {'status': values['status']}
        else: raise AssertionError('Unexpected native command')
        return json.dumps(result).encode()
    node = ApplicationNodeExecutor(profiles=rig.supervisor.profiles, cluster_uuid=identity['cluster_uuid'],
        local_node='proxmox', run_command=run)
    return node, values, identity


def test_owner_uses_native_config_json_and_exact_marker(native):
    node, values, identity = native
    assert node.assert_owner(identity)
    assert all(v[0] == '/usr/bin/pvesh' for v in values['calls'])


@pytest.mark.parametrize('bad', ['qemu', 'pool', 'privileged', 'foreign-marker', 'apparmor', 'mount', 'device', 'hook', 'features', 'large'])
def test_incompatible_guest_cannot_receive_any_effect(native, bad):
    node, values, identity = native
    if bad == 'qemu': values['resource']['type'] = 'qemu'
    if bad == 'pool': values['resource']['pool'] = 'other-pool'
    if bad == 'privileged': values['config']['unprivileged'] = 0
    if bad == 'foreign-marker': values['config']['description'] = '{"nap":{}}'
    if bad == 'apparmor': values['config']['lxc.apparmor.profile'] = 'unconfined'
    if bad == 'mount': values['config']['mp0'] = '/node,path=/host'
    if bad == 'device': values['config']['dev0'] = '/dev/kvm'
    if bad == 'hook': values['config']['hookscript'] = 'local:snippets/unsafe.sh'
    if bad == 'features': values['config']['features'] = 'nesting=1,keyctl=1,mount=nfs'
    if bad == 'large': values['config']['memory'] = 2048
    with pytest.raises(JobError): node.enable_environment(identity)
    assert not any(v[0] == '/usr/sbin/pct' for v in values['calls'])


def test_docker_features_are_a_fixed_action_on_an_owned_stopped_guest(native):
    node, values, identity = native
    node.enable_environment(identity)
    node.enable_environment(identity)
    assert sum(v[0] == '/usr/sbin/pct' for v in values['calls']) == 1


def test_running_guest_is_not_stopped_to_change_features(native):
    node, values, identity = native
    values['status'] = 'running'
    with pytest.raises(JobError): node.enable_environment(identity)
    assert not any(v[0] == '/usr/sbin/pct' for v in values['calls'])


def test_cleanup_never_touches_a_reused_or_live_vmid(native):
    node,values,identity=native
    with pytest.raises(JobError):node.assert_absent(identity)
    # An unavailable/malformed observation is not absence.
    node.run_command=lambda *args,**kwargs:b'{}'
    with pytest.raises(JobError):node.assert_absent(identity)
    node.run_command=lambda *args,**kwargs:json.dumps([{'vmid':str(identity['vmid'])}]).encode()
    with pytest.raises(JobError):node.assert_absent(identity)


def test_cleanup_observes_clusterwide_absence_without_requiring_enabled_old_profile(native):
    node,values,identity=native
    node.run_command=lambda *args,**kwargs:b'[]'
    node.assert_absent(identity)
    with pytest.raises(JobError):node.assert_absent(identity|{'cluster_uuid':'foreign'})
