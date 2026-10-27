"""Assembly for the installed node package. No settings come from SSH argv/env."""
import importlib
import os
from pathlib import Path
import re
import stat
import sys

from .credentials import CredentialChannel
from .network import NetworkRegistry
from .protocol import JobError, strict_json
from .spool import Spool
from .state import PrivateDirectory, StateStore, uuid_text
from .supervisor import Supervisor, SystemdService
from ..profiles.registry import ProfileRegistry


class StrategyLoader:
    MODULES = {'imagen_docker': 'docker.deploy', 'community_scripts': 'community.deploy'}

    def available(self, origin):
        relative = self.MODULES.get(origin)
        if relative is None: return False
        path = Path(__file__).absolute().parents[1].joinpath(*relative.split('.')).with_suffix('.py')
        try:
            info = path.lstat()
            return (stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid in {0, os.geteuid()}
                    and not info.st_mode & 0o022 and path.parent.resolve() == path.parent)
        except OSError: return False

    def get(self, origin):
        if not self.available(origin): return None
        def deploy(context):
            try:
                prefix = __package__.rsplit('.', 1)[0]
                module = importlib.import_module(prefix+'.'+self.MODULES[origin])
                action = getattr(module, 'deploy')
                if not callable(action): raise JobError('PROFILE_UNAVAILABLE')
            except (ImportError, AttributeError):
                raise JobError('PROFILE_UNAVAILABLE') from None
            return action(context)
        return deploy


class RuntimeProfiles:
    """A certificate cannot make an absent strategy or changed platform usable."""
    def __init__(self, registry, *, available, context=None):
        self.registry, self.available, self.context = registry, available, context or {}

    def capabilities(self):
        values = self.registry.capabilities()
        for value in values:
            if value['estado'] != 'habilitado': continue
            try:
                definition = self.registry.require({k: value[k] for k in ('id','revision','sha256')}, **self.context)
                if not self.available(definition['origen']):
                    value.update(estado='bloqueado', motivo_codigo='DEPENDENCY_UNAVAILABLE')
            except JobError:
                value.update(estado='bloqueado', motivo_codigo='PLATFORM_CHANGED')
        return values

    def require(self, reference, **context):
        definition = self.registry.require(reference, **{**context, **self.context})
        if not self.available(definition['origen']): raise JobError('PROFILE_UNAVAILABLE')
        return definition


def _config(path):
    try:
        path = Path(path)
        with PrivateDirectory(path.parent, create=False) as folder:
            descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=folder.fd)
            with os.fdopen(descriptor, 'rb') as source:
                info = os.fstat(source.fileno()); folder._private_file(info)
                if info.st_size > 1048576: raise ValueError()
                value = strict_json(source.read(1048577))
        if (set(value) not in ({'schema_version', 'cluster_uuid', 'node', 'profiles'},
                             {'schema_version', 'cluster_uuid', 'node', 'profiles', 'networks'})
                or value['schema_version'] != 'nap-application-node/1'
                or type(value['node']) is not str or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,99}', value['node'])): raise ValueError()
        uuid_text(value['cluster_uuid']); ProfileRegistry(value['profiles'])
        NetworkRegistry(value.get('networks', {}), cluster_uuid=value['cluster_uuid'], node=value['node'])
        return value
    except Exception: raise JobError('PROFILE_UNAVAILABLE') from None


def _node_factory(**kwargs):
    if __package__.startswith('infra.'):
        from infra.runner.node_executor import ApplicationNodeExecutor
    else:
        root = Path('/opt/nap/runner')
        info = root.lstat()
        if root.resolve() != root or info.st_uid != 0 or info.st_mode & 0o022: raise JobError('UNCONFIRMED')
        sys.path.insert(0, str(root))
        from node_executor import ApplicationNodeExecutor
    # The installed adapter derives the actual local node from /etc/pve/local;
    # the configuration's node name is compared by build_runtime below.
    kwargs.pop('local_node', None)
    return ApplicationNodeExecutor(**kwargs)


class NodeRuntime:
    def __init__(self, *, supervisor, credentials, strategies, node):
        self.supervisor, self.credentials, self.strategies, self.node = supervisor, credentials, strategies, node
        self._spools = {}
        supervisor.spool_factory = self.spool

    def spool(self, execution_id):
        execution_id = uuid_text(execution_id)
        if execution_id not in self._spools:
            self._spools[execution_id] = Spool(store=self.supervisor.store, execution_id=execution_id)
        return self._spools[execution_id]

    def emitter(self, execution_id):
        spool = self.spool(execution_id)
        return lambda event: spool.append_safe(**event)

    def __enter__(self): return self
    def __exit__(self, *args):
        self.credentials.close(); self.supervisor.store.close()


def build_runtime(*, config_path=Path('/etc/nap/applications-011/runner.json'),
                  state_dir=Path('/var/lib/nap-application-jobs'), source_dir=Path('/run/nap-application-jobs'),
                  node_factory=_node_factory):
    value = _config(config_path)
    strategies = StrategyLoader()
    profiles = RuntimeProfiles(ProfileRegistry(value['profiles']), available=strategies.available)
    state = credentials = None
    try:
        node = node_factory(profiles=profiles, cluster_uuid=value['cluster_uuid'], local_node=value['node'])
        node.networks = NetworkRegistry(value.get('networks', {}), cluster_uuid=value['cluster_uuid'], node=value['node'])
        # Fixed local private paths, loaded only if a real job needs material.
        from .tls import InstanceTLS
        node.tls_factory = InstanceTLS.from_node
        if node.local_node != value['node']: raise JobError('IDENTITY_MISMATCH')
        platform = node.platform()
        profiles.context = {'cluster_uuid': value['cluster_uuid'], 'node': value['node'], 'platform': platform}
        state = StateStore(state_dir, create=False)
        credentials = CredentialChannel(source_root=source_dir, create=False)
        supervisor = Supervisor(store=state, profiles=profiles, service=SystemdService(run_command=node.run_command),
            credentials=credentials, assert_owner=node.assert_owner, cluster_uuid=value['cluster_uuid'], node=value['node'], platform=platform)
        return NodeRuntime(supervisor=supervisor, credentials=credentials, strategies=strategies, node=node)
    except Exception:
        if state is not None: state.close()
        if credentials is not None: credentials.close()
        raise JobError('UNCONFIRMED') from None
