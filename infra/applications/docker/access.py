"""Read the node's pull credential; it never belongs to an application offer."""
import os
from pathlib import Path
import re
import ssl

from ..job.protocol import JobError,strict_json
from ..job.state import PrivateDirectory


def registry_credentials(image,*,directory=Path('/etc/nap/applications-011/registries')):
    name=image['registry_profile_id'];host=image['repositorio'].split('/')[0]
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,63}',name):raise JobError('PROFILE_UNAVAILABLE')
    path=Path(directory)/(name+'.json')
    if not path.exists() and not path.is_symlink() and name=='docker-hub' and host=='docker.io':
        return {'reference_host':'docker.io','ca_pem':None,'username':None,'password':None}
    try:
        with PrivateDirectory(directory,create=False) as folder:
            descriptor=os.open(name+'.json',os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=folder.fd)
            with os.fdopen(descriptor,'rb') as source:
                folder._private_file(os.fstat(source.fileno()))
                value=strict_json(source.read(32769),limit=32768)
        if (set(value)!={'schema_version','registry_profile_id','reference_host','repository_prefixes','ca_pem','username','password'}
                or value['schema_version']!='nap-registry-credential/1' or value['registry_profile_id']!=name
                or value['reference_host']!=host or type(value['repository_prefixes'])is not list
                or not 1<=len(value['repository_prefixes'])<=50):raise ValueError()
        repository=image['repositorio'].split('/',1)[1]
        if (any(type(p)is not str or not re.fullmatch(r'(?:[a-z0-9]+(?:[._-][a-z0-9]+)*/)+',p) for p in value['repository_prefixes'])
                or not any(repository.startswith(p) for p in value['repository_prefixes'])):raise ValueError()
        for field in ('username','password'):
            if type(value[field])is not str or not value[field] or len(value[field])>4096 or '\x00'in value[field]:raise ValueError()
        if value['ca_pem'] is not None:
            if type(value['ca_pem'])is not str or 'PRIVATE KEY'in value['ca_pem']:raise ValueError()
            ssl.create_default_context(cadata=value['ca_pem'])
        return {key:value[key] for key in ('reference_host','ca_pem','username','password')}
    except Exception:raise JobError('PROFILE_UNAVAILABLE') from None
