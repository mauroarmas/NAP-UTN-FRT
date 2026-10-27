from copy import deepcopy
from hashlib import sha256
from uuid import uuid4

import pytest

from infra.applications.job.isolation import IsolationManager
from infra.applications.job.protocol import canonical,JobError
from infra.applications.job.network import table_name
from infra.applications.tests.test_network_policy import policy


@pytest.fixture
def guard(tmp_path,policy):
    folder=tmp_path/'isolation';folder.mkdir(mode=0o700)
    owner={'resource_uuid':policy['resource_uuid'],'cluster_uuid':str(uuid4()),'nonce_sha256':'a'*64,'vmid':policy['vmid']}
    boot=str(uuid4());manager=IsolationManager(directory=folder,boot_id=boot)
    state={'table':None,'effects':0,'stopped':True}
    def stopped():
        if not state['stopped']:raise JobError('UNCONFIRMED')
    def install():
        state['effects']+=1
        if state['table'] is not None:raise JobError('UNCONFIRMED')
        state['table']={'nftables':[{'metainfo':{'json_schema_version':1}},
            {'table':{'family':'bridge','name':table_name(policy),'handle':3,'comment':'nap011:'+sha256(canonical(policy)).hexdigest()}},
            {'rule':{'family':'bridge','table':table_name(policy),'chain':'outgoing','handle':7,'expr':[{'counter':{'packets':0,'bytes':0}},{'drop':None}]}}]}
    def observe():
        if state['table'] is None:raise JobError('UNCONFIRMED')
        return deepcopy(state['table'])
    return manager,owner,state,{'assert_stopped':stopped,'install':install,'observe':observe}


def test_replay_only_reuses_a_durable_exact_owned_table_ignoring_counters(guard,policy):
    manager,owner,state,actions=guard
    assert manager.ensure(owner,policy,**actions)
    state['table']['nftables'][2]['rule']['expr'][0]['counter']={'packets':19,'bytes':400}
    state['table']['nftables'][2]['rule']['handle']=99
    assert manager.ensure(owner,policy,**actions) and state['effects']==1


@pytest.mark.parametrize('mutation',['foreign','rule','policy','running'])
def test_changed_identity_rules_or_running_guest_never_get_overwritten(guard,policy,mutation):
    manager,owner,state,actions=guard
    manager.ensure(owner,policy,**actions)
    if mutation=='foreign':owner['nonce_sha256']='b'*64
    if mutation=='rule':state['table']['nftables'][2]['rule']['expr']=[{'accept':None}]
    if mutation=='policy':policy['service_port']=9999
    if mutation=='running':state['stopped']=False
    with pytest.raises(JobError):manager.ensure(owner,policy,**actions)
    assert state['effects']==1


def test_unconfirmed_install_is_not_repeated_or_adopted(guard,policy):
    manager,owner,state,actions=guard
    original=actions['install']
    def lost():original();raise JobError('UNCONFIRMED')
    with pytest.raises(JobError):manager.ensure(owner,policy,**{**actions,'install':lost})
    with pytest.raises(JobError):manager.ensure(owner,policy,**actions)
    assert state['effects']==1


def test_reboot_can_recreate_missing_table_only_for_same_owned_stopped_resource(guard,policy):
    manager,owner,state,actions=guard
    manager.ensure(owner,policy,**actions)
    state['table']=None
    reboot=IsolationManager(directory=manager.directory,boot_id=str(uuid4()))
    assert reboot.ensure(owner,policy,**actions) and state['effects']==2
