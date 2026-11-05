from functools import partial
from uuid import uuid4

from infra.applications.job.credentials import CredentialChannel
from infra.applications.job.selfcheck import child, CheckStore
from infra.applications.job.spool import Spool


def test_install_check_retires_private_source_and_console_after_ack(tmp_path, monkeypatch):
    execution = str(uuid4()); canary = 'private-canary-installation-011'
    state = tmp_path/'state'; state.mkdir(mode=0o700)
    copies = tmp_path/'copies'; copies.mkdir(mode=0o700)
    factory = partial(CredentialChannel, source_root=tmp_path/'source', credentials_root=copies)
    with factory() as channel:
        channel.stage(execution, fingerprint='a'*64, secretos={'CANARY': canary})
        copy = copies/('nap-application-'+execution+'.service'); copy.mkdir(mode=0o700)
        (copy/'deployment').write_bytes((channel.path/('credential.'+execution+'.json')).read_bytes())
        (copy/'deployment').chmod(0o400)
    with CheckStore(state/('selfcheck.'+execution)) as store:
        store.write('job',execution,{'identity':{'resource_uuid':execution},'fingerprint':'a'*64,
            'last_source_seq':0,'acknowledged_seq':0,'worker_finished':False,'loaded':False,'checked':False})
    monkeypatch.setenv('CREDENTIALS_DIRECTORY',str(copy))
    child(execution, state_root=state, channel_factory=factory)
    with CheckStore(state/('selfcheck.'+execution),create=False) as store:
        proof = store.read_job(execution)
        assert all(proof[k] for k in ('loaded','source_removed','spool_safe','replay','ack_retired','checked'))
        assert Spool(store=store,execution_id=execution).summary_locked(proof)['acknowledged_seq'] == 1
        assert all(canary.encode() not in p.read_bytes() for p in store.path.iterdir())
