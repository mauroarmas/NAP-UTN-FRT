"""Fixed runtime policy and argv builders; application commands remain in the image."""
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
from uuid import UUID

from ..job.protocol import JobError,canonical

ROOT=Path(__file__).resolve().parents[1]


def trusted_bytes(path):
    path=Path(path)
    try:
        info=path.lstat()
        # Reviewed checkout sources may use the workspace's shared group umask.
        # The installed worker imports only `applications.*` under /opt/nap and
        # always requires non-writable group/other bits (installer uses 0444).
        writable=0o002 if __package__=='infra.applications.docker' else 0o022
        if (path.resolve()!=path or info.st_uid not in {0,os.geteuid()} or info.st_mode&writable
                or not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_size>1048576):raise ValueError()
        return path.read_bytes()
    except Exception:raise JobError('PROFILE_UNAVAILABLE') from None


def policy():
    try:
        value=json.loads(trusted_bytes(ROOT/'profiles/docker/ubuntu24.json'))
        if (set(value)!={'schema_version','estado','base','packages','storage_driver','filesystem','minimum_resources','edge'}
                or value['schema_version']!='nap-docker-runtime/1' or value['estado']!='pendiente_validacion'
                or set(value['packages'])!={'docker','containerd','runc'}
                or any(not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.+:~_-]{0,99}',v) for v in value['packages'].values())
                or value['storage_driver'] not in {'overlayfs','overlay2'} or value['filesystem']!='ext4'
                or value['minimum_resources']!={'vcpus':2,'ram_mb':1024,'disk_gb':8}
                or value['edge']['arquitectura']!=value['base']['arquitectura']):raise ValueError()
        return value
    except Exception:raise JobError('PROFILE_UNAVAILABLE') from None


def policy_digest():
    # Logical paths and bytes are identical in checkout and installed package.
    paths={str(p.relative_to(ROOT)):p for p in (ROOT/'job').glob('*.py') if p.name!='__init__.py'}
    paths.update({name:ROOT/name for name in ('docker/runtime.py','docker/contract.py','docker/guest.py','docker/deploy.py',
        'docker/access.py','docker/probes.py','profiles/docker/ubuntu24.json','schemas/nap-deployment-1.json')})
    paths['runner/node_executor.py']=ROOT.parent/'runner/node_executor.py'
    contract=ROOT/'profiles/profile_contract.py'
    if not contract.exists():contract=ROOT.parents[1]/'backend/app/schemas/application_profiles.py'
    paths['profiles/profile_contract.py']=contract
    return sha256(canonical({name:sha256(trusted_bytes(path)).hexdigest() for name,path in sorted(paths.items())})).hexdigest()


def validate_profile(profile):
    lock=policy()
    expected={**lock['packages'],'storage_driver':lock['storage_driver']}
    if (profile['origen']!='imagen_docker' or profile['base']!=lock['base'] or profile['runtime']!=expected
            or profile['minimum_resources']!=lock['minimum_resources']
            or profile['policy_bundle_sha256']!=policy_digest()):raise JobError('PROFILE_UNAVAILABLE')
    return lock


from .contract import volume_name,application_arguments
