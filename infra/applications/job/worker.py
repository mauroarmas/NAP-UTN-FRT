"""Fixed detached entry point. Strategies are institutional Python adapters.

Guest programs are separate children, never imported as host code. This module
does not run a host Community wrapper or accept executable names from a request.
"""
import os
from pathlib import Path
import signal
import stat
import sys
import time
from uuid import UUID


if not __package__:
    # Python -I excludes the script directory. Add only the verified installed root.
    try:
        expected = Path('/opt/nap/applications/job/worker.py')
        if os.geteuid() != 0 or len(sys.argv) != 2 or Path(__file__).absolute() != expected: raise ValueError()
        for path in [*reversed(expected.parents), expected]:
            info = path.lstat()
            if (info.st_uid != 0 or info.st_mode & 0o022 or stat.S_ISLNK(info.st_mode)
                    or not (stat.S_ISDIR(info.st_mode) if path != expected else stat.S_ISREG(info.st_mode))): raise ValueError()
        sys.dont_write_bytecode = True
        sys.path.insert(0, '/opt/nap')
        __package__ = 'applications.job'
    except Exception:
        raise SystemExit(1) from None

from .protocol import JobError
from .redaction import ClosedOutput, SecretRedactor
from .state import uuid_text

PHASE_MESSAGES = {'preparacion': 'Preparando aplicación.', 'creacion': 'Creando recurso.',
    'entorno': 'Habilitando entorno.', 'instalacion': 'Instalando aplicación.',
    'configuracion': 'Configurando aplicación.', 'arranque': 'Iniciando aplicación.',
    'comprobacion': 'Comprobando acceso.'}


def retry_transition(action):
    """Retry a short metadata transition, never a strategy or guest command."""
    deadline = time.monotonic()+3
    while True:
        try: return action()
        except JobError as exc:
            if exc.code != 'UNCONFIRMED' or time.monotonic() >= deadline: raise
            time.sleep(0.025)


class WorkerContext:
    def __init__(self, *, supervisor, job, invocation_id, values, emit, node=None):
        self.supervisor, self.configuration = supervisor, job['configuracion']
        self.identity = job['identity']
        self._execution = self.identity['execution_id']
        self._binding = {'fingerprint': job['fingerprint'], 'boot_id': job['node_boot_id'], 'invocation_id': invocation_id}
        self._values, self._emit = values, emit
        self._output = ClosedOutput(values.values())
        self._closed_streams = set()
        self._phase = job['fase']
        self.dropped_messages = 0
        self.node = node
        self.network = None
        self.tls = None
        self._runtime_secrets = []

    def secret(self, name):
        if type(name) is not str or name not in self._values: raise JobError('INVALID_REQUEST')
        return self._values[name]

    def _safe_emit(self, stream, text):
        try:
            if self._emit({'fase': self._phase, 'stream': stream, 'texto_depurado': text}) is False:
                self.dropped_messages += 1
        except JobError as exc:
            if exc.code == 'DEADLINE_EXCEEDED': raise
            self.dropped_messages += 1
        except Exception: self.dropped_messages += 1  # Console loss never blocks an installer.

    def phase(self, fase):
        if type(fase) is not str or fase not in PHASE_MESSAGES: raise JobError('INVALID_REQUEST')
        retry_transition(lambda: self.supervisor.phase(self._execution, **self._binding, fase=fase))
        self._phase = fase
        safe = SecretRedactor(self._values.values()).feed(PHASE_MESSAGES[fase].encode(), final=True)
        self._safe_emit('sistema', safe)

    def output(self, stream, raw, *, final=False):
        if type(stream) is not str or stream in self._closed_streams: raise JobError('INVALID_REQUEST')
        for text in self._output.feed(stream, raw, final=final): self._safe_emit(stream, text)
        if final: self._closed_streams.add(stream)

    def flush(self):
        for stream in ('stdout', 'stderr'):
            if stream not in self._closed_streams: self.output(stream, b'', final=True)

    def begin_output(self, *, extra_secrets=(), packages=frozenset()):
        """Register a child's complete secret set before executing that child."""
        self.flush()
        self._output = ClosedOutput([*self._values.values(), *self._runtime_secrets, *extra_secrets], packages=packages)
        self._closed_streams.clear()


class ApplicationWorker:
    def __init__(self, *, supervisor, credentials, strategies, emit, node=None):
        self.supervisor, self.credentials = supervisor, credentials
        self.strategies, self.emit = strategies, emit
        self.node = node

    def run(self, execution_id, *, invocation_id):
        context = None
        try:
            execution_id = uuid_text(execution_id); invocation_id = uuid_text(invocation_id)
            job = self.supervisor.store.read_job(execution_id)
            if job is None: raise JobError('UNCONFIRMED')
            binding = {'fingerprint': job['fingerprint'], 'boot_id': job['node_boot_id'], 'invocation_id': invocation_id}
            # A systemd service can reach exec before its short admission lock is
            # released. Retry only the idempotent claim, never the installer body.
            def claim():
                return retry_transition(lambda: self.supervisor.claim_worker(execution_id, **binding))
            values = self.credentials.load_and_retire(execution_id, fingerprint=job['fingerprint'], mark_loaded=claim)
            if values is None: return 0
            context = WorkerContext(supervisor=self.supervisor, job=job, invocation_id=invocation_id, values=values, emit=self.emit, node=self.node)
            self.supervisor.profiles.require(job['identity']['perfil'], cluster_uuid=self.supervisor.cluster_uuid,
                node=self.supervisor.node, platform=self.supervisor.platform)
            strategy = self.strategies.get(job['configuracion']['origen'])
            if not callable(strategy): raise JobError('PROFILE_UNAVAILABLE')
            context.phase('entorno')
            if self.node is not None:
                environment = self.node.prepare_application(context.identity, context.configuration)
                context.network, context.tls = environment['network'], environment['tls']
                context._runtime_secrets.append(context.tls['private_key_pem'])
                context.begin_output()
            result = strategy(context)
            if context._phase != 'comprobacion': raise JobError('UNCONFIRMED')
            context.flush()
            retry_transition(lambda: self.supervisor.complete(execution_id, **binding, resultado=result))
            return 0
        except Exception as exc:
            # Only a claimed worker writes an outcome. Unknown startup/copy state
            # is reconciled by status after the unit exits, without another start.
            if context is not None:
                try:
                    context.flush()
                    code = exc.code if isinstance(exc, JobError) else 'UNCONFIRMED'
                    if code in {'UNCONFIRMED', 'DEADLINE_EXCEEDED'}:
                        retry_transition(lambda: self.supervisor.uncertain(execution_id, **binding, error_codigo=code))
                    else:
                        retry_transition(lambda: self.supervisor.complete(execution_id, **binding, error_codigo=code))
                except Exception: pass  # Never fall back to a raw traceback/file.
            return 1


def main():
    """The installed runtime supplies fixed adapters, profiles and a safe spool."""
    if os.geteuid() != 0 or len(sys.argv) != 2: return 1
    try:
        execution = uuid_text(sys.argv[1])
        invocation = str(UUID(os.environ['INVOCATION_ID']))
        from .runtime import build_runtime
        def deadline(*args): raise JobError('DEADLINE_EXCEEDED')
        signal.signal(signal.SIGTERM, deadline)
        with build_runtime() as runtime:
            return ApplicationWorker(supervisor=runtime.supervisor, credentials=runtime.credentials,
                strategies=runtime.strategies, emit=runtime.emitter(execution), node=runtime.node).run(execution, invocation_id=invocation)
    except Exception:
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
