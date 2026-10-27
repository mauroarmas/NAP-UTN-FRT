"""Durable admission and observation of a detached application installer.

No strategy runs in the SSH process. A lost response, a new lease or a vanished
unit never causes another start. Native success alone never confirms delivery.
"""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import re
from uuid import UUID

from .protocol import (JobError, PROTOCOL, PHASES, ERROR_CODES, canonical, fingerprint,
                       parse_request, parse_response, public_identity)
from .state import STATUS_KEYS, uuid_text


def _boot_id():
    try:
        return uuid_text(Path('/proc/sys/kernel/random/boot_id').read_text()[:64].strip())
    except (OSError, ValueError): raise JobError('UNCONFIRMED') from None


def _now(): return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


class SystemdService:
    """Fixed units, binary and credential path; run_command is a bounded adapter."""
    def __init__(self, *, run_command): self.run_command = run_command

    @staticmethod
    def unit(execution_id): return 'nap-application-' + uuid_text(execution_id) + '.service'

    def start(self, execution_id, *, timeout_seconds):
        if type(timeout_seconds) is not int or timeout_seconds != 2700: raise JobError('PROFILE_UNAVAILABLE')
        unit = self.unit(execution_id)
        credential = '/run/nap-application-jobs/credential.' + execution_id + '.json'
        argv = ['/usr/bin/systemd-run', '--quiet', '--no-ask-password', '--no-block', '--unit='+unit,
            '--property=Type=exec', '--property=Restart=no', '--property=UMask=0077',
            '--property=StandardInput=null', '--property=StandardOutput=null', '--property=StandardError=null',
            '--property=NoNewPrivileges=yes', '--property=KillMode=control-group', '--property=TimeoutStopSec=10s',
            '--property=RuntimeMaxSec='+str(timeout_seconds), '--property=LoadCredential=deployment:'+credential,
            '--', '/usr/bin/python3', '-I', '/opt/nap/applications/job/worker.py', execution_id]
        try: self.run_command(argv, timeout=12, limit=8192)
        except Exception:
            # systemd may already have accepted the unit. Do not kill/retry it.
            raise JobError('UNCONFIRMED') from None

    def observe(self, execution_id):
        argv = ['/usr/bin/systemctl', 'show', self.unit(execution_id), '--no-pager',
            '--property=LoadState', '--property=ActiveState', '--property=InvocationID', '--property=Result']
        try:
            # systemctl returns 1 for a missing unit, whose closed LoadState is
            # precisely the observation required before a first admission.
            raw = self.run_command(argv, timeout=5, limit=8192, accepted_codes=(0,1))
            if type(raw) is not bytes or len(raw) > 8192: raise ValueError()
            values = {}
            for line in raw.decode('ascii').splitlines():
                key, value = line.split('=', 1)
                if key in values: raise ValueError()
                values[key] = value
            if set(values) != {'LoadState', 'ActiveState', 'InvocationID', 'Result'}: raise ValueError()
            if values['LoadState'] == 'not-found': return {'state': 'absent', 'invocation_id': None, 'result': None}
            if values['LoadState'] != 'loaded': raise ValueError()
            invocation = str(UUID(values['InvocationID'])) if values['InvocationID'] else None
            state = {'active': 'active', 'activating': 'starting', 'inactive': 'inactive',
                     'failed': 'inactive', 'deactivating': 'inactive'}.get(values['ActiveState'])
            if state is None: raise ValueError()
            result = 'timeout' if values['Result'] == 'timeout' else None
            return {'state': state, 'invocation_id': invocation, 'result': result}
        except Exception:
            raise JobError('UNCONFIRMED') from None


class Supervisor:
    def __init__(self, *, store, profiles, service, credentials, assert_owner,
                 cluster_uuid, node, platform, boot_id=_boot_id, now=_now, spool_factory=None):
        self.store, self.profiles, self.service = store, profiles, service
        self.credentials, self.assert_owner = credentials, assert_owner
        self.cluster_uuid, self.node, self.platform = uuid_text(cluster_uuid), node, deepcopy(platform)
        self.boot_id, self.now = boot_id, now
        self.spool_factory = spool_factory

    def _owner(self, identity):
        try:
            if self.assert_owner(deepcopy(identity)) is not True: raise JobError('IDENTITY_MISMATCH')
        except JobError: raise
        except Exception: raise JobError('UNCONFIRMED') from None

    def _context(self, request):
        if request['cluster_uuid'] != self.cluster_uuid or request['node'] != self.node:
            raise JobError('IDENTITY_MISMATCH')

    def _match(self, job, request):
        if request['lease_generation'] < job['controller_generation']: raise JobError('STALE_CONTROLLER')
        if request['action'] == 'start' and job['fingerprint'] != fingerprint(request): raise JobError('EXECUTION_CONFLICT')
        identity = public_identity(request); identity.pop('lease_generation')
        if identity != job['identity']: raise JobError('IDENTITY_MISMATCH')

    def _resource_job(self, resource_uuid):
        entry = self.store.read('resource', resource_uuid)
        if entry is None: return None
        if (set(entry) != {'schema_version', 'resource_uuid', 'execution_id'}
                or entry['schema_version'] != 'nap-job-resource/1' or entry['resource_uuid'] != resource_uuid):
            raise JobError('UNCONFIRMED')
        previous = self.store.read_job(uuid_text(entry['execution_id']))
        if previous is None or previous['identity']['resource_uuid'] != resource_uuid: raise JobError('UNCONFIRMED')
        return previous

    def _observe(self, job):
        if job['estado'] in {'confirmado', 'fallido'} or job['worker_finished']: return
        if job['node_boot_id'] != uuid_text(self.boot_id()):
            job.update(estado='incierto', error_codigo='UNCONFIRMED'); return
        try:
            observation = self.service.observe(job['identity']['execution_id'])
            if type(observation) is not dict or set(observation) != {'state', 'invocation_id', 'result'}: raise ValueError()
            invocation = observation['invocation_id']
            if invocation is not None: uuid_text(invocation)
            if job['unit_invocation_id'] is not None and invocation != job['unit_invocation_id']: raise ValueError()
            if observation['state'] == 'active' and invocation is not None:
                job.update(estado='ejecutando', error_codigo=None, unit_invocation_id=invocation, dispatch_state='observado')
            elif observation['state'] == 'starting' and invocation is not None:
                job['unit_invocation_id'] = invocation
            else:
                job.update(estado='incierto', error_codigo='DEADLINE_EXCEEDED' if observation['result'] == 'timeout' else 'UNCONFIRMED')
        except Exception:
            job.update(estado='incierto', error_codigo='UNCONFIRMED')

    def _response(self, job, request, *, console=None):
        data = {**public_identity(request), **{k: deepcopy(job[k]) for k in STATUS_KEYS}}
        if console is not None: data.update(console)
        response = {'protocol': PROTOCOL, 'ok': True, 'action': request['action'], 'data': data}
        return parse_response(canonical(response), request=request)

    def _refresh(self, job, request):
        self._match(job, request)
        job['controller_generation'] = request['lease_generation']
        self._observe(job)
        console = None
        if request['action'] in {'read', 'ack'} and self.spool_factory is None: raise JobError('UNCONFIRMED')
        if self.spool_factory is not None:
            spool = self.spool_factory(request['execution_id'])
            if request['action'] == 'ack':
                # Fence the controller durably before purging text. A subsequent
                # metadata write failure must not let an old controller through.
                job['updated_at'] = self.now(); self.store.write_job(job)
                spool.ack_locked(job, through_seq=request['through_seq'])
            job.update(spool.summary_locked(job))
            if request['action'] == 'read':
                console = spool.read_locked(job, after=request['after'], limit_bytes=request['limit_bytes'])
        job['updated_at'] = self.now()
        self.store.write_job(job)
        if job['credentials_loaded']:
            self.credentials.discard(request['execution_id'], fingerprint=job['fingerprint'])
        return self._response(job, request, console=console)

    def handle(self, raw):
        request = parse_request(raw)
        if request['action'] == 'profiles':
            response = {'protocol': PROTOCOL, 'ok': True, 'action': 'profiles',
                        'data': {'profiles': self.profiles.capabilities()}}
            return parse_response(canonical(response), request=request)
        self._context(request)
        if request['action'] == 'start': return self._start(request)
        # Unknown readers do not create lock files or manufacture an execution.
        job = self.store.read_job(request['execution_id'])
        if job is None: raise JobError('UNCONFIRMED')
        self._match(job, request)
        with self.store.lock('resource', request['resource_uuid']):
            job = self.store.read_job(request['execution_id'])
            if job is None: raise JobError('UNCONFIRMED')
            return self._refresh(job, request)

    def _start(self, request):
        with self.store.lock('node'), self.store.lock('resource', request['resource_uuid']):
            existing = self.store.read_job(request['execution_id'])
            if existing is not None: return self._refresh(existing, request)
            profile = self.profiles.require(request['perfil'], cluster_uuid=self.cluster_uuid,
                node=self.node, platform=self.platform)
            config = request['configuracion']
            if (config['base'] != profile['base'] or config['origen'] != profile['origen']
                    or any(config['minimum_resources'][k] < v for k, v in profile['minimum_resources'].items())):
                raise JobError('PROFILE_UNAVAILABLE')
            identity = public_identity(request); identity.pop('lease_generation')
            self._owner(identity)
            previous = self._resource_job(request['resource_uuid'])
            if previous is not None:
                if (previous['estado'] != 'fallido' or previous['identity']['operacion_raiz_id'] != request['operacion_raiz_id']
                        or previous['identity']['configuracion_sha256'] != request['configuracion_sha256']):
                    raise JobError('EXECUTION_CONFLICT')
            # The manifest also binds operation/attempt when a crash interrupted
            # publication of the resource index. An index alone is not admission.
            history = self.store.jobs()
            for old in history:
                other = old['identity']
                if other['operation_id'] == request['operation_id'] or other['intento_id'] == request['intento_id']:
                    raise JobError('EXECUTION_CONFLICT')
                if other['resource_uuid'] == request['resource_uuid'] and old['estado'] in {'preparado', 'ejecutando', 'incierto'}:
                    raise JobError('EXECUTION_CONFLICT')
            # Count uncertain executions too; only reconciliation may release them.
            active = sum(j['estado'] in {'preparado', 'ejecutando', 'incierto'} for j in history)
            if active >= profile['max_active_jobs_per_node']: raise JobError('PROFILE_UNAVAILABLE')
            if self.service.observe(request['execution_id'])['state'] != 'absent': raise JobError('EXECUTION_CONFLICT')
            stamp = self.now()
            job = {'schema_version': 'nap-job-state/1', 'identity': identity,
                'configuracion': deepcopy(config), 'secreto_referencias': deepcopy(request['secreto_referencias']),
                'fingerprint': fingerprint(request), 'controller_generation': request['lease_generation'],
                'node_boot_id': uuid_text(self.boot_id()), 'unit_invocation_id': None,
                'dispatch_state': 'guardado', 'credentials_loaded': False, 'worker_finished': False, 'estado': 'preparado',
                'fase': 'preparacion', 'last_source_seq': 0, 'acknowledged_seq': 0,
                'resultado': None, 'error_codigo': None, 'created_at': stamp, 'updated_at': stamp}
            self.store.write_job(job)
            self.store.write('resource', request['resource_uuid'], {'schema_version': 'nap-job-resource/1',
                'resource_uuid': request['resource_uuid'], 'execution_id': request['execution_id']})
            try:
                self.credentials.stage(request['execution_id'], fingerprint=job['fingerprint'], secretos=request['secretos'])
                self._owner(identity)
                job['dispatch_state'] = 'solicitado'; self.store.write_job(job)
            except Exception as exc:
                job.update(estado='fallido', error_codigo=exc.code if isinstance(exc, JobError) else 'UNCONFIRMED', updated_at=self.now())
                self.store.write_job(job)
                self.credentials.discard(request['execution_id'], fingerprint=job['fingerprint'])
                return self._response(job, request)
            try:
                # Short admission only: systemd owns the installer after enqueue.
                self.service.start(request['execution_id'], timeout_seconds=profile['install_timeout_seconds'])
                self._owner(identity)
                self._observe(job)
            except Exception:
                job.update(estado='incierto', error_codigo='UNCONFIRMED')
            job['updated_at'] = self.now(); self.store.write_job(job)
            return self._response(job, request)

    def claim_worker(self, execution_id, *, fingerprint, boot_id, invocation_id):
        """One effective installer per execution, independent of controller leases."""
        job = self.store.read_job(uuid_text(execution_id))
        if job is None: raise JobError('UNCONFIRMED')
        with self.store.lock('resource', job['identity']['resource_uuid']):
            job = self.store.read_job(execution_id)
            if (job is None or job['fingerprint'] != fingerprint or job['node_boot_id'] != boot_id
                    or uuid_text(self.boot_id()) != boot_id): raise JobError('IDENTITY_MISMATCH')
            invocation_id = uuid_text(invocation_id)
            observed = self.service.observe(execution_id)
            if (observed['state'] not in {'active', 'starting'} or observed['invocation_id'] != invocation_id
                    or job['unit_invocation_id'] not in {None, invocation_id}): raise JobError('IDENTITY_MISMATCH')
            if job['credentials_loaded'] or job['estado'] in {'confirmado', 'fallido'}: return False
            self._owner(job['identity'])
            job.update(credentials_loaded=True, unit_invocation_id=invocation_id, dispatch_state='observado',
                       estado='ejecutando', error_codigo=None, updated_at=self.now())
            self.store.write_job(job)
            return True

    def phase(self, execution_id, *, fingerprint, boot_id, invocation_id, fase):
        phases = ('preparacion', 'creacion', 'entorno', 'instalacion', 'configuracion', 'arranque', 'comprobacion')
        if fase not in phases: raise JobError('INVALID_REQUEST')
        job = self.store.read_job(uuid_text(execution_id))
        if job is None: raise JobError('UNCONFIRMED')
        with self.store.lock('resource', job['identity']['resource_uuid']):
            job = self.store.read_job(execution_id)
            if (job is None or job['fingerprint'] != fingerprint or job['node_boot_id'] != boot_id
                    or uuid_text(self.boot_id()) != boot_id or job['unit_invocation_id'] != invocation_id
                    or not job['credentials_loaded'] or job['worker_finished'] or job['estado'] not in {'ejecutando', 'incierto'}):
                raise JobError('IDENTITY_MISMATCH')
            if job['fase'] not in phases or phases.index(fase) < phases.index(job['fase']): raise JobError('UNCONFIRMED')
            self._owner(job['identity'])
            job.update(fase=fase, estado='ejecutando', error_codigo=None, updated_at=self.now())
            self.store.write_job(job)

    def uncertain(self, execution_id, *, fingerprint, boot_id, invocation_id, error_codigo='UNCONFIRMED'):
        if error_codigo not in {'UNCONFIRMED', 'DEADLINE_EXCEEDED'}: raise JobError('INVALID_REQUEST')
        job = self.store.read_job(uuid_text(execution_id))
        if job is None: raise JobError('UNCONFIRMED')
        with self.store.lock('resource', job['identity']['resource_uuid']):
            job = self.store.read_job(execution_id)
            if (job is None or job['fingerprint'] != fingerprint or job['node_boot_id'] != boot_id
                    or uuid_text(self.boot_id()) != boot_id or job['unit_invocation_id'] != invocation_id
                    or not job['credentials_loaded']): raise JobError('IDENTITY_MISMATCH')
            if job['estado'] in {'confirmado', 'fallido'}: return
            if job['worker_finished']:
                if job['error_codigo'] != error_codigo: raise JobError('EXECUTION_CONFLICT')
                return
            job.update(estado='incierto', worker_finished=True, error_codigo=error_codigo, updated_at=self.now())
            self.store.write_job(job)

    def complete(self, execution_id, *, fingerprint, boot_id, invocation_id, resultado=None, error_codigo=None):
        job = self.store.read_job(uuid_text(execution_id))
        if job is None: raise JobError('UNCONFIRMED')
        with self.store.lock('resource', job['identity']['resource_uuid']):
            job = self.store.read_job(execution_id)
            if (job is None or job['fingerprint'] != fingerprint or job['node_boot_id'] != boot_id
                    or uuid_text(self.boot_id()) != boot_id or job['unit_invocation_id'] != uuid_text(invocation_id)
                    or not job['credentials_loaded']): raise JobError('IDENTITY_MISMATCH')
            state = 'fallido' if error_codigo is not None else 'confirmado'
            if job['estado'] in {'confirmado', 'fallido'}:
                if (job['estado'], job['resultado'], job['error_codigo']) != (state, resultado, error_codigo):
                    raise JobError('EXECUTION_CONFLICT')
                return
            if job['worker_finished']: raise JobError('EXECUTION_CONFLICT')
            self._owner(job['identity'])
            observed = self.service.observe(execution_id)
            if observed.get('result') == 'timeout': raise JobError('DEADLINE_EXCEEDED')
            if observed.get('state') != 'active' or observed.get('invocation_id') != invocation_id:
                raise JobError('UNCONFIRMED')
            if state == 'confirmado':
                expected = 'acceso_web' if job['configuracion']['access']['tipo'] == 'web' else 'autenticacion_tcp'
                if (type(resultado) is not dict or type(resultado.get('comprobaciones')) is not list
                        or not {'aislamiento', 'runtime', 'salud', expected} <= set(resultado['comprobaciones'])
                        or resultado.get('recurso_configurado') is not True): raise JobError('UNCONFIRMED')
            elif error_codigo not in ERROR_CODES or resultado is not None: raise JobError('INVALID_REQUEST')
            job.update(estado=state, worker_finished=True, resultado=deepcopy(resultado), error_codigo=error_codigo,
                       fase='finalizada', updated_at=self.now())
            self.store.write_job(job)
