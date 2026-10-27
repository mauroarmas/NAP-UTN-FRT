from pathlib import Path

import pytest

from infra.applications.job.worker import ApplicationWorker
from infra.applications.job.credentials import CredentialChannel
from infra.applications.job.protocol import JobError
from infra.applications.tests.test_job_credentials import systemd_copy
from infra.applications.tests.test_job_supervisor import rig, call


RESULT = {'comprobaciones': ['aislamiento', 'runtime', 'salud', 'acceso_web'], 'recurso_configurado': True}


@pytest.fixture
def worker_rig(rig, tmp_path, monkeypatch):
    copies = tmp_path / 'credentials'; copies.mkdir(mode=0o700)
    channel = CredentialChannel(source_root=tmp_path/'source', credentials_root=copies)
    rig.credentials = channel; rig.supervisor.credentials = channel
    first = call(rig)
    systemd_copy(channel, rig.request['execution_id'], monkeypatch)
    rig.invocation = rig.service.units[rig.request['execution_id']]['invocation_id']
    rig.first = first; rig.messages = []
    yield rig
    channel.close()


def build(rig, strategy, *, sink=None):
    return ApplicationWorker(supervisor=rig.supervisor, credentials=rig.credentials,
        strategies={'imagen_docker': strategy}, emit=rig.messages.append if sink is None else sink)


def test_detached_worker_runs_once_and_status_remains_readable_during_install(worker_rig):
    rig = worker_rig; effects = []
    def strategy(context):
        effects.append(context.configuration['origen'])
        context.phase('instalacion')
        assert call(rig, 'status')['fase'] == 'instalacion'
        assert context.secret('APP_PASSWORD') == 'fixture-private-password-011'
        assert not list(rig.credentials.path.iterdir())  # Source was removed before installer effects.
        context.output('stdout', b'password=fixture-private-password-011\n')
        context.phase('comprobacion')
        return RESULT
    worker = build(rig, strategy)
    assert worker.run(rig.request['execution_id'], invocation_id=rig.invocation) == 0
    assert worker.run(rig.request['execution_id'], invocation_id=rig.invocation) == 0
    assert effects == ['imagen_docker'] and call(rig, 'status')['estado'] == 'confirmado'
    assert 'fixture-private-password-011' not in str(rig.messages)
    assert any('Salida omitida' in m['texto_depurado'] for m in rig.messages)


@pytest.mark.parametrize('kind,expected', [('dependency', 'fallido'), ('deadline', 'incierto'), ('unknown', 'incierto')])
def test_failure_result_is_durable_safe_and_not_an_automatic_reinstall(worker_rig, kind, expected):
    rig = worker_rig; effects = []
    def strategy(context):
        effects.append('entered'); context.phase('instalacion')
        if kind == 'dependency': raise JobError('DEPENDENCY_UNAVAILABLE')
        if kind == 'deadline': raise JobError('DEADLINE_EXCEEDED')
        raise RuntimeError('fixture-private-password-011')
    worker = build(rig, strategy)
    assert worker.run(rig.request['execution_id'], invocation_id=rig.invocation) == 1
    assert rig.store.read_job(rig.request['execution_id'])['estado'] == expected
    assert 'fixture-private-password-011' not in str(rig.messages)
    worker.run(rig.request['execution_id'], invocation_id=rig.invocation)
    assert effects == ['entered']


def test_console_storage_failure_does_not_interrupt_installer(worker_rig):
    rig = worker_rig; seen = []
    def failing_sink(_): raise OSError('fixture disk full')
    def strategy(context):
        context.phase('instalacion'); context.phase('comprobacion')
        seen.append(context.dropped_messages)
        return RESULT
    assert build(rig, strategy, sink=failing_sink).run(rig.request['execution_id'], invocation_id=rig.invocation) == 0
    assert seen[0] > 0 and call(rig, 'status')['estado'] == 'confirmado'


def test_wrong_unit_cannot_claim_or_consume_the_credential_source(worker_rig):
    rig = worker_rig
    worker = build(rig, lambda context: pytest.fail('Installer must not run'))
    from uuid import uuid4
    assert worker.run(rig.request['execution_id'], invocation_id=str(uuid4())) == 1
    assert list(rig.credentials.path.iterdir())  # Unknown caller cannot delete the source.
    assert not rig.store.read_job(rig.request['execution_id'])['credentials_loaded']


def test_environment_is_required_before_strategy_and_private_tls_never_reaches_console(worker_rig):
    from types import SimpleNamespace
    rig=worker_rig; order=[]
    tls_key='fixture-TLS-private-material-011'
    def prepare(identity,config):
        order.append('isolation')
        return {'network':{'host':'app81.nap.test'},'tls':{'private_key_pem':tls_key}}
    def strategy(context):
        order.append('installer')
        assert context.network['host']=='app81.nap.test'
        context.begin_output()
        context.output('stdout',tls_key.encode(),final=True)
        context.phase('comprobacion')
        return RESULT
    worker=ApplicationWorker(supervisor=rig.supervisor,credentials=rig.credentials,
        strategies={'imagen_docker':strategy},emit=rig.messages.append,node=SimpleNamespace(prepare_application=prepare))
    assert worker.run(rig.request['execution_id'],invocation_id=rig.invocation)==0
    assert order==['isolation','installer']
    assert tls_key not in str(rig.messages)


def test_isolation_failure_prevents_installer_and_guest_start(worker_rig):
    from types import SimpleNamespace
    rig=worker_rig; installed=[]
    def prepare(*args): raise JobError('UNCONFIRMED')
    worker=ApplicationWorker(supervisor=rig.supervisor,credentials=rig.credentials,
        strategies={'imagen_docker':lambda context:installed.append(True)},emit=rig.messages.append,
        node=SimpleNamespace(prepare_application=prepare))
    assert worker.run(rig.request['execution_id'],invocation_id=rig.invocation)==1
    assert not installed
    assert rig.store.read_job(rig.request['execution_id'])['estado']=='incierto'
