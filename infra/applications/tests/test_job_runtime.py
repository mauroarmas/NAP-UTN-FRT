import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from infra.applications.job.runtime import build_runtime, StrategyLoader, RuntimeProfiles
from infra.applications.job.protocol import JobError, canonical
from infra.applications.profiles.registry import ProfileRegistry
from infra.applications.tests.test_application_profiles import certify, reference


def test_unbuilt_strategy_is_explicitly_unavailable_even_if_profile_file_says_enabled(profile_entry):
    entry = certify(profile_entry)
    profiles = RuntimeProfiles(ProfileRegistry({'docker-ubuntu24:1': entry}), available=lambda origin: False)
    assert profiles.capabilities()[0]['estado'] == 'bloqueado'
    assert profiles.capabilities()[0]['motivo_codigo'] == 'DEPENDENCY_UNAVAILABLE'
    with pytest.raises(JobError, match='PROFILE_UNAVAILABLE'): profiles.require(reference(entry))
    assert StrategyLoader().get('arbitrary_python_module') is None


def test_runtime_opens_prepared_fixed_directories_and_never_enables_profiles(tmp_path):
    config = tmp_path / 'config'; config.mkdir(mode=0o700)
    source = config/'runner.json'
    cluster = str(uuid4())
    source.write_bytes(canonical({'schema_version': 'nap-application-node/1', 'node': 'proxmox', 'cluster_uuid': cluster, 'profiles': {}}))
    source.chmod(0o600)
    for name in ('state', 'run'): (tmp_path/name).mkdir(mode=0o700)
    def node_factory(**kwargs):
        assert kwargs['cluster_uuid'] == cluster
        return SimpleNamespace(local_node='proxmox', platform=lambda: {'pve': '9.2.2','kernel':'fixture','arquitectura':'amd64'},
            assert_owner=lambda identity: True, run_command=lambda *args, **kw: pytest.fail('No systemd effect expected'))
    with build_runtime(config_path=source, state_dir=tmp_path/'state', source_dir=tmp_path/'run', node_factory=node_factory) as runtime:
        result = runtime.supervisor.handle(b'{"protocol":"nap-application-job/1","action":"profiles"}')
        assert result['data']['profiles'] == []
        store = runtime.supervisor.store
        assert store.jobs() == []
    assert store.fd is None


def test_invalid_private_config_is_not_echoed_or_used_to_create_state(tmp_path):
    source = tmp_path/'runner.json'
    source.write_text('{"schema_version":"invalid","password":"fixture-do-not-echo"}'); source.chmod(0o600)
    with pytest.raises(JobError) as caught:
        build_runtime(config_path=source, state_dir=tmp_path/'state', source_dir=tmp_path/'run')
    assert 'fixture-do-not-echo' not in str(caught.value)
    assert not (tmp_path/'state').exists()
