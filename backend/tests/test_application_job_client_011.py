import asyncio
from copy import deepcopy
from hashlib import sha256
from uuid import uuid4

import pytest

from app.services.application_job_client import ApplicationJobClient
from infra.applications.job.protocol import JobError, canonical, fingerprint, public_identity
from tests.test_guest_runner_client import runner_config


@pytest.fixture
def job_request(documento_docker):
    config = deepcopy(documento_docker)
    return {'protocol':'nap-application-job/1','action':'start',
        **{key:str(uuid4()) for key in ('operation_id','operacion_raiz_id','intento_id','execution_id','cluster_uuid','resource_uuid')},
        'lease_generation':1,'node':'pve1','vmid':101,'pool':'nap-apps','nonce':'e'*64,
        'configuracion_sha256':sha256(canonical(config)).hexdigest(),'perfil':config['perfil'],
        'configuracion':config,'secretos':{'APP_PASSWORD':'private-app-secret-011'},
        'secreto_referencias':[{'id':str(uuid4()),'nombre':'APP_PASSWORD','revision':1}]}


def query(request, action='status'):
    return {k:v for k,v in request.items() if k not in {'configuracion','secretos','secreto_referencias'}}|{'action':action}


def response(request, fp):
    return {'protocol':request['protocol'],'ok':True,'action':request['action'],'data':{
        **public_identity(request),'fingerprint':fp,'node_boot_id':str(uuid4()),'estado':'ejecutando',
        'fase':'instalacion','last_source_seq':0,'acknowledged_seq':0,'resultado':None,'error_codigo':None}}


class Process:
    def __init__(self, output=b'', *, wait=False, exit_code=0):
        self.returncode = None if wait else exit_code
        self.output, self.block, self.killed = output, wait, False
    async def communicate(self, input=None):
        self.input = input
        if self.block: await asyncio.Event().wait()
        return self.output,b'private remote error must never be retained'
    def kill(self): self.killed=True
    async def wait(self): self.returncode=-9


async def test_start_keeps_values_and_nonce_only_on_private_stdin_and_correlates_response(job_request,runner_config,caplog):
    process=Process(canonical(response(job_request,fingerprint(job_request))))
    captured={}
    async def start(*argv,**kwargs): captured.update(argv=argv,kwargs=kwargs);return process
    result=await ApplicationJobClient(config=runner_config,start_process=start).execute(job_request)
    assert result['ok'] and result['data']['nonce_sha256']==sha256(job_request['nonce'].encode()).hexdigest()
    assert process.input==canonical(job_request)
    assert all(secret not in repr(captured)+caplog.text for secret in (job_request['nonce'],job_request['secretos']['APP_PASSWORD']))
    assert 'StrictHostKeyChecking=yes' in captured['argv'] and captured['argv'][-1]=='nap-guest-runner'
    assert captured['kwargs']['start_new_session'] and captured['kwargs']['stderr']==asyncio.subprocess.DEVNULL


@pytest.mark.parametrize('action', ['start','ack','status','read'])
async def test_lost_response_only_retries_queries_and_retires_local_transport(job_request,runner_config,action):
    calls=[]
    request=job_request if action=='start' else query(job_request,action)
    if action=='ack': request['through_seq']=0
    if action=='read': request.update(after=0,limit_bytes=65536)
    async def start(*args,**kwargs):
        p=Process(wait=True);calls.append(p);return p
    with pytest.raises(JobError,match='UNCONFIRMED'):
        await ApplicationJobClient(config=runner_config,start_process=start,timeout_seconds=0.01).execute(
            request,expected_fingerprint=fingerprint(job_request))
    assert len(calls)==(2 if action in {'status','read'} else 1)
    assert all(p.killed for p in calls)


@pytest.mark.parametrize('mutation', ['generation','identity','fingerprint','private','oversize','nonce'])
async def test_response_mismatch_or_raw_output_is_never_accepted_or_retried(job_request,runner_config,mutation,caplog):
    request=query(job_request);fp=fingerprint(job_request);value=response(request,fp)
    if mutation=='generation': value['data']['lease_generation']+=1
    if mutation=='identity': value['data']['execution_id']=str(uuid4())
    if mutation=='fingerprint': value['data']['fingerprint']='f'*64
    if mutation=='private': value['data']['password']='private-output-011'
    if mutation=='nonce': value['data']['nonce']=job_request['nonce']
    raw=canonical(value) if mutation!='oversize' else b'x'*131073
    calls=[]
    async def start(*args,**kwargs): calls.append(args);return Process(raw)
    with pytest.raises(JobError) as caught:
        await ApplicationJobClient(config=runner_config,start_process=start,query_retries=0).execute(request,expected_fingerprint=fp)
    assert len(calls)==1 and 'private-output-011' not in str(caught.value)+caplog.text


async def test_capabilities_require_configured_node_and_never_use_browser_destination(runner_config):
    calls=[]
    async def start(*args,**kwargs):
        calls.append(args)
        return Process(canonical({'protocol':'nap-application-job/1','ok':True,'action':'profiles','data':{'profiles':[]}}))
    client=ApplicationJobClient(config=runner_config,start_process=start)
    request={'protocol':'nap-application-job/1','action':'profiles'}
    for node in (None,'https://untrusted.example','root@pve1'):
        with pytest.raises(JobError): await client.execute(request,node=node)
    assert not calls
    assert (await client.execute(request,node='pve1'))['data']['profiles']==[]


async def test_cancellation_closes_local_ssh_without_new_dispatch(job_request,runner_config):
    created=asyncio.Event();process=Process(wait=True)
    async def start(*args,**kwargs):created.set();return process
    task=asyncio.create_task(ApplicationJobClient(config=runner_config,start_process=start).execute(job_request))
    await asyncio.wait_for(created.wait(),timeout=1);task.cancel()
    with pytest.raises(asyncio.CancelledError): await task
    assert process.killed


async def test_explicit_node_and_expected_fingerprint_cannot_override_approved_request(job_request,runner_config):
    calls=[]
    async def start(*args,**kwargs):calls.append(args);raise AssertionError()
    client=ApplicationJobClient(config=runner_config,start_process=start)
    for request,kwargs in [(job_request,{'node':'other'}),(job_request,{'expected_fingerprint':'f'*64}),(query(job_request),{})]:
        with pytest.raises(JobError):await client.execute(request,**kwargs)
    assert not calls
