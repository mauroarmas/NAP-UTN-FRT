"""Durable ownership receipt for a single resource's host firewall table."""
from hashlib import sha256
from uuid import UUID

from .network import compile_policy,table_name
from .protocol import JobError,canonical
from .state import StateStore


def normalized(value,depth=0):
    if depth>32:raise JobError('UNCONFIRMED')
    if type(value) is list:return [normalized(v,depth+1) for v in value if not(type(v)is dict and set(v)=={'metainfo'})]
    if type(value) is dict:
        result={}
        for key,item in value.items():
            if key=='handle':continue
            if key=='counter' and type(item) is dict and set(item)=={'packets','bytes'}:
                if any(type(v)is not int or v<0 for v in item.values()):raise JobError('UNCONFIRMED')
                result[key]={}
            else:result[key]=normalized(item,depth+1)
        return result
    if type(value) not in {str,int,bool,type(None)}:raise JobError('UNCONFIRMED')
    return value


class IsolationManager:
    def __init__(self,*,directory,boot_id):
        self.directory=directory
        if str(UUID(boot_id))!=boot_id:raise JobError('UNCONFIRMED')
        self.boot_id=boot_id

    def ensure(self,identity,policy,*,assert_stopped,install,observe):
        name=table_name(policy);policy_sha=sha256(canonical(policy)).hexdigest()
        binding={key:identity[key] for key in ('cluster_uuid','resource_uuid','nonce_sha256','vmid')}
        def fingerprint():
            value=observe()
            tables=[v['table'] for v in value['nftables'] if type(v)is dict and 'table'in v]
            if (len(tables)!=1 or tables[0].get('family')!='bridge' or tables[0].get('name')!=name
                    or tables[0].get('comment')!='nap011:'+policy_sha):raise JobError('UNCONFIRMED')
            return sha256(canonical(normalized(value))).hexdigest()
        with StateStore(self.directory,create=False) as store:
            with store.lock('resource',identity['resource_uuid']):
                assert_stopped()
                row=store.read('credential',identity['resource_uuid'])
                if row is not None:
                    if (set(row)!={'schema_version','binding','policy_sha256','state','boot_id','nft_sha256'}
                            or row['schema_version']!='nap-isolation/1' or row['binding']!=binding
                            or row['policy_sha256']!=policy_sha or row['state']!='applied'
                            or type(row['nft_sha256'])is not str or len(row['nft_sha256'])!=64):raise JobError('UNCONFIRMED')
                    try:actual=fingerprint()
                    except JobError:
                        if row['boot_id']==self.boot_id:raise
                    else:
                        if actual!=row['nft_sha256']:raise JobError('UNCONFIRMED')
                        return True
                row={'schema_version':'nap-isolation/1','binding':binding,'policy_sha256':policy_sha,
                    'state':'planned','boot_id':self.boot_id,'nft_sha256':None}
                store.write('credential',identity['resource_uuid'],row)
                # Exclusive create refuses any unrelated or unconfirmed table.
                install()
                row.update(state='applied',nft_sha256=fingerprint())
                store.write('credential',identity['resource_uuid'],row)
                return True
