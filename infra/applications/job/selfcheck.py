"""Explicit root-only installation check; never dispatched by the SSH protocol.

Exercises real systemd credential delivery and the sanitized spool, without a
guest, profile validation, registry request or application installation.
"""
from contextlib import suppress
from hashlib import sha256
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import time
from uuid import uuid4

from .credentials import CredentialChannel
from .protocol import JobError
from .redaction import ClosedOutput, SUPPRESSED
from .spool import Spool
from .state import StateStore, uuid_text

STATE_ROOT = Path('/var/lib/nap-application-jobs')


class CheckStore(StateStore):
    """Isolated test metadata, deliberately not a deployment manifest."""
    def read_job(self, execution_id):
        return self.read('job', execution_id)


def child(execution_id, *, state_root=STATE_ROOT, channel_factory=CredentialChannel):
    uuid_text(execution_id)
    with CheckStore(state_root/('selfcheck.'+execution_id), create=False) as store:
        job = store.read_job(execution_id)
        def mark_loaded():
            if job['loaded']: return False
            job['loaded'] = True
            store.write('job', execution_id, job)
            return True
        with channel_factory(create=False) as channel:
            values = channel.load_and_retire(execution_id, fingerprint=job['fingerprint'], mark_loaded=mark_loaded)
            if values is None: raise JobError('UNCONFIRMED')
            source_removed = channel.read('credential', execution_id) is None
        redactor = ClosedOutput(values.values())
        raw = (values['CANARY']+'\n').encode()
        # Deliberately split the private value across every streamed byte.
        safe = []
        for byte in raw: safe += redactor.feed('stdout', bytes([byte]))
        safe += redactor.feed('stdout', b'', final=True)
        if safe != [SUPPRESSED]: raise JobError('UNCONFIRMED')
        spool = Spool(store=store, execution_id=execution_id)
        if not spool.append_safe(fase='comprobacion', stream='stdout', texto_depurado=safe[0]):
            raise JobError('UNCONFIRMED')
        with store.lock('resource', execution_id):
            page = spool.read_locked(job, after=0, limit_bytes=65536)
            replay = spool.read_locked(job, after=0, limit_bytes=65536)
            if page != replay or len(page['items']) != 1: raise JobError('UNCONFIRMED')
            spool.ack_locked(job, through_seq=1)
            retired = spool.read_locked(job, after=0, limit_bytes=65536)['items'] == []
        job.update(source_removed=source_removed, spool_safe=True, replay=True, ack_retired=retired,
                   worker_finished=True, checked=True)
        store.write('job', execution_id, job)


def run():
    if os.geteuid() != 0: raise JobError('UNCONFIRMED')
    execution_id = str(uuid4())
    from .runtime import build_runtime
    with build_runtime() as runtime:
        if runtime.supervisor.service.observe(execution_id)['state'] != 'absent': raise JobError('UNCONFIRMED')
    unit = 'nap-application-'+execution_id+'.service'
    scope = STATE_ROOT/('selfcheck.'+execution_id)
    canary = secrets.token_urlsafe(48)
    fingerprint = sha256(('installation-check:'+execution_id).encode()).hexdigest()
    job = {'identity': {'resource_uuid': execution_id}, 'fingerprint': fingerprint,
           'last_source_seq': 0, 'acknowledged_seq': 0, 'worker_finished': False,
           'loaded': False, 'checked': False}
    with CheckStore(scope) as store: store.write('job', execution_id, job)
    with CredentialChannel(create=False) as channel:
        channel.stage(execution_id, fingerprint=fingerprint, secretos={'CANARY': canary})
    call = lambda argv, **kw: subprocess.run(argv, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=kw.get('timeout', 5), check=True)
    started = False
    try:
        code = "import sys;sys.path.insert(0,'/opt/nap');from applications.job.selfcheck import child;child(sys.argv[1])"
        call(['/usr/bin/systemd-run', '--quiet', '--no-ask-password', '--no-block', '--unit='+unit,
            '--property=Type=exec', '--property=Restart=no', '--property=UMask=0077',
            '--property=StandardInput=null', '--property=StandardOutput=null', '--property=StandardError=null',
            '--property=NoNewPrivileges=yes', '--property=KillMode=control-group',
            '--property=RuntimeMaxSec=20', '--property=TimeoutStopSec=3s',
            '--property=LoadCredential=deployment:/run/nap-application-jobs/credential.'+execution_id+'.json',
            '--', '/usr/bin/python3', '-I', '-c', code, execution_id])
        started = True
        deadline = time.monotonic()+25
        while time.monotonic() < deadline:
            with CheckStore(scope, create=False) as store: proof = store.read_job(execution_id)
            state = call(['/usr/bin/systemctl','show',unit,'--property=ActiveState','--value']).stdout.strip()
            if state in {b'inactive', b'failed'}: break
            time.sleep(0.1)
        else: raise JobError('DEADLINE')
        if not all(proof.get(k) is True for k in ('loaded','source_removed','spool_safe','replay','ack_retired','checked')):
            raise JobError('UNCONFIRMED')
        journal = call(['/usr/bin/journalctl','--unit='+unit,'--no-pager','--output=cat','--lines=100'], timeout=15).stdout
        if len(journal) > 131072: raise JobError('UNCONFIRMED')
        artifacts = [p.read_bytes() for p in scope.iterdir() if p.is_file()]
        if any(canary.encode() in data for data in [journal, *artifacts]): raise JobError('UNCONFIRMED')
        with CredentialChannel(create=False) as channel:
            if channel.read('credential', execution_id) is not None: raise JobError('UNCONFIRMED')
        if (Path('/run/credentials')/unit).exists(): raise JobError('UNCONFIRMED')
        return {'scope': 'real_node_common_mechanics', 'credential_delivered': True,
                'missing_unit_observation': True,
                'private_source_retired': True, 'systemd_copy_retired': True,
                'journal_and_spool_without_canary': True, 'console_replay_and_ack': True,
                'profiles_enabled': [], 'guests_created': False}
    finally:
        if started:
            with suppress(Exception): call(['/usr/bin/systemctl','stop',unit])
            with suppress(Exception): call(['/usr/bin/systemctl','reset-failed',unit])
        with CredentialChannel(create=False) as channel:
            channel.discard(execution_id, fingerprint=fingerprint)
        # Only this unpredictable, newly-created test namespace is retired.
        shutil.rmtree(scope)
