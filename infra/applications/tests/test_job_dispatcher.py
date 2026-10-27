from contextlib import contextmanager
from copy import deepcopy

from infra.runner.nap_guest_runner import is_application_request, handle_application_request
from infra.applications.job.protocol import canonical, parse_response
from infra.applications.tests.test_job_supervisor import rig


def test_new_protocol_dispatch_is_closed_and_preserves_same_execution(rig):
    @contextmanager
    def runtime():
        yield type('Runtime', (), {'supervisor': rig.supervisor})()
    assert is_application_request(canonical(rig.request))
    result = handle_application_request(canonical(rig.request), runtime_factory=runtime)
    assert parse_response(canonical(result), request=rig.request)['data']['estado'] == 'ejecutando'
    assert handle_application_request(canonical(rig.request), runtime_factory=runtime)['data']['execution_id'] == rig.request['execution_id']
    assert len(rig.service.starts) == 1
    assert not is_application_request(b'{"protocol":"nap-guest-runner/1"}')
    assert not is_application_request(b'{"protocol":"nap-build-runner/1"}')


def test_invalid_action_or_free_command_cannot_open_the_runtime(rig):
    def forbidden(): raise AssertionError('Runtime must not be loaded for an invalid request')
    for key, value in [('command', 'sh -c arbitrary'), ('action', 'exec'), ('unit', 'sshd.service')]:
        invalid = {**rig.request, key: value}
        result = handle_application_request(canonical(invalid), runtime_factory=forbidden)
        assert result == {'protocol':'nap-application-job/1','ok':False,'error':'INVALID_REQUEST'}


def test_runtime_error_never_echoes_credentials_or_internal_paths(rig):
    def failure(): raise RuntimeError('private-source /etc/nap/private fixture-secret')
    result = handle_application_request(canonical(rig.request), runtime_factory=failure)
    assert result == {'protocol':'nap-application-job/1','ok':False,'error':'UNCONFIRMED'}
