#!/usr/bin/env python3
"""Explicit root-only gate for the final strategy; never an SSH runner action.

Pending profiles remain pending in the production registry. This separate gate
accepts one sealed candidate, reserved VMID and nonce, using the actual worker,
credentials, supervisor, spool and systemd properties. It cannot publish offers.
"""
import argparse
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from hashlib import sha256
import json
import os
import re
from pathlib import Path
import secrets
import shlex
import subprocess
import sys
from uuid import UUID,uuid4

BASE=Path('/root/nap011-final-docker-gate')
VMID=900011
POOL='nap011-final-gate'


def encode(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()


def save(value):
    temporary=BASE/'context.new'
    descriptor=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(descriptor,'wb') as target:target.write(encode(value));target.flush();os.fsync(target.fileno())
        os.replace(temporary,BASE/'context.json')
    finally:temporary.unlink(missing_ok=True)


def load():
    path=BASE/'context.json';info=path.lstat()
    if path.resolve()!=path or info.st_uid!=0 or info.st_mode&0o077 or info.st_size>1048576:raise ValueError('UNTRUSTED_GATE')
    value=json.loads(path.read_bytes())
    if value['purpose']!='final_docker_strategy' or value['request']['vmid']!=VMID or value['request']['pool']!=POOL:raise ValueError('INVALID_GATE')
    return value


def call(args,*,timeout=20):
    return subprocess.run(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
        check=True,timeout=timeout).stdout


def pve(path,**params):
    argv=['/usr/bin/pvesh','get',path,'--output-format','json']
    for key,value in params.items():argv+=['--'+key.replace('_','-'),str(value)]
    return json.loads(call(argv))


def assets():
    sys.dont_write_bytecode=True
    sys.path.insert(0,'/opt/nap')
    sys.path.insert(0,'/opt/nap/runner')
    from applications.docker.runtime import policy,policy_digest
    return policy(),policy_digest()


def config_marker(context):
    request=context['request']
    return {'nap':{'cluster_uuid':request['cluster_uuid'],'resource_uuid':request['resource_uuid'],
        'nonce_sha256':sha256(request['nonce'].encode()).hexdigest(),'pool':POOL,
        'definition_sha256':request['configuracion_sha256'],'bundle_sha256':context['profile']['policy_bundle_sha256']}}


def owned(context):
    matches=[v for v in pve('/cluster/resources',type='vm') if v['vmid']==VMID]
    if not matches:return None
    row=matches[0];node=context['request']['node']
    if len(matches)!=1 or row.get('type')!='lxc' or row.get('node')!=node or row.get('pool')!=POOL:raise ValueError('FOREIGN_GUEST')
    config=pve('/nodes/'+node+'/lxc/'+str(VMID)+'/config')
    if json.loads(config['description'])!=config_marker(context) or config.get('unprivileged')!=1:raise ValueError('FOREIGN_GUEST')
    if (config.get('cores')!=2 or config.get('memory')!=1024
            or not re.fullmatch(r'local-lvm:vm-900011-disk-[0-9]+(?:,[A-Za-z0-9=.,_-]+)?',config.get('rootfs',''))
            or any(re.fullmatch(r'(?:mp|dev)[0-9]+',key) or key.startswith('lxc') or key=='hookscript' for key in config)):
        raise ValueError('UNEXPECTED_GUEST_CONFIGURATION')
    return config


def initialize(data):
    if (BASE/'context.json').exists():raise ValueError('EXISTING_GATE_REQUIRES_CLEANUP')
    if any(v['vmid']==VMID for v in pve('/cluster/resources',type='vm')):raise ValueError('VMID_BUSY')
    if pve('/nodes/proxmox/storage/local-lvm/content',vmid=VMID):raise ValueError('VMID_DISKS_BUSY')
    lock,bundle=assets()
    archive=Path('/var/lib/vz/template/cache')/lock['base']['volumen_lxc'].split('/')[-1]
    if archive.resolve()!=archive or not archive.is_file():raise ValueError('BASE_UNAVAILABLE')
    checksum=sha256()
    with archive.open('rb') as source:
        while chunk:=source.read(1048576):checksum.update(chunk)
    if checksum.hexdigest()!=lock['base']['sha256']:raise ValueError('BASE_CHANGED')
    from node_executor import ApplicationNodeExecutor
    node=ApplicationNodeExecutor(profiles=None,cluster_uuid=data['cluster_uuid'])
    definition={'id':'docker-ubuntu24','revision':1,'origen':'imagen_docker','base':lock['base'],
        'cluster_uuid':data['cluster_uuid'],'nodes':['proxmox'],'platform':node.platform(),
        'runtime':{**lock['packages'],'storage_driver':lock['storage_driver']},'features':['nesting=1','keyctl=1'],
        'security':{'unprivileged':True,'apparmor':'enforce','seccomp':True},'minimum_resources':lock['minimum_resources'],
        'network_profile_id':'lab-applications-011','policy_bundle_sha256':bundle,'install_timeout_seconds':2700,'max_active_jobs_per_node':2}
    reference={'id':definition['id'],'revision':definition['revision'],'sha256':sha256(encode(definition)).hexdigest()}
    document={'schema_version':'nap-deployment/1','origen':'imagen_docker','modelo_servicio':'saas','perfil':reference,
        'base':lock['base'],'minimum_resources':lock['minimum_resources'],
        'access':{'tipo':'web','puerto':data['port'],'politica':'web-managed','upstream':'http',
            'probe':{'tipo':'http','path':data['probe_path'],'estados':[200],'timeout_segundos':10},'websocket':False},
        'variables':{},'secretos':[{'nombre':'NAP_CANARY_VALUE','etiqueta':'Prueba privada','modo':'generado'}],
        'persistencia':data['persistencia'],'imagen':data['image']}
    # NAP_ is reserved for applications. A plain declared name exercises the
    # private channel without granting an image an internal control variable.
    document['secretos'][0]['nombre']='APP_PRIVATE_VALUE'
    from applications.job.configuration import validate_configuration
    document=validate_configuration(document)
    request={'protocol':'nap-application-job/1','action':'start',
        **{key:str(uuid4()) for key in ('operation_id','operacion_raiz_id','intento_id','execution_id','resource_uuid')},
        'cluster_uuid':data['cluster_uuid'],'node':'proxmox','vmid':VMID,'pool':POOL,'nonce':secrets.token_hex(32),
        'lease_generation':1,'perfil':reference,'configuracion':document,'configuracion_sha256':sha256(encode(document)).hexdigest(),
        'secreto_referencias':[{'id':str(uuid4()),'nombre':'APP_PRIVATE_VALUE','revision':1}]}
    network=data['network']
    from applications.job.network import NetworkRegistry
    NetworkRegistry({'lab-applications-011':network},cluster_uuid=data['cluster_uuid'],node='proxmox')
    slot=sorted(network['slots'].values(),key=lambda v:v['address'])[0]
    if slot['address']!='172.16.36.81':raise ValueError('UNEXPECTED_LAB_SLOT')
    value={'purpose':'final_docker_strategy','created_at':datetime.now(timezone.utc).isoformat(),
        'deadline_at':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),'profile':definition,'request':request,
        'network':network,'slot':slot,'phase':'sealed','create_requested':False,'job_requested':False}
    save(value)
    return {'state':'candidate_sealed','profiles_enabled':False,'vmid':VMID,'policy_sha256':bundle}


def runtime(context):
    assets()
    from applications.job.protocol import JobError,canonical
    from applications.job.configuration import validate_configuration
    from applications.docker.runtime import validate_profile
    from applications.profiles.profile_contract import validate_definition
    from applications.job.supervisor import Supervisor,SystemdService
    from applications.job.state import StateStore
    from applications.job.credentials import CredentialChannel
    from applications.job.runtime import NodeRuntime,StrategyLoader
    from applications.job.network import NetworkRegistry
    from applications.job.isolation import IsolationManager
    from applications.job.tls import InstanceTLS
    from node_executor import ApplicationNodeExecutor,bounded_command
    request=context['request'];definition=context['profile']
    class PendingGate:
        def require(self,reference,**scope):
            if datetime.now(timezone.utc)>=datetime.fromisoformat(context['deadline_at']):raise JobError('PROFILE_UNAVAILABLE')
            if reference!=request['perfil']:raise JobError('PROFILE_UNAVAILABLE')
            validate_definition(definition);validate_profile(definition)
            if sha256(canonical(definition)).hexdigest()!=reference['sha256']:raise JobError('PROFILE_UNAVAILABLE')
            if any(scope.get(k,v)!=v for k,v in [('cluster_uuid',definition['cluster_uuid']),('node','proxmox'),('platform',definition['platform'])]):raise JobError('PROFILE_UNAVAILABLE')
            return deepcopy(definition)
        def capabilities(self):return [{**request['perfil'],'estado':'pendiente_validacion','motivo_codigo':'VALIDATION_REQUIRED'}]
    class GateNode(ApplicationNodeExecutor):
        def _configuration(self,identity):
            if any(identity.get(k)!=request[k] for k in ('resource_uuid','vmid','node','pool','cluster_uuid','configuracion_sha256')):raise JobError('IDENTITY_MISMATCH')
            return super()._configuration(identity)
    profiles=PendingGate()
    node=GateNode(profiles=profiles,cluster_uuid=request['cluster_uuid'])
    if node.platform()!=definition['platform']:raise JobError('PROFILE_UNAVAILABLE')
    node.networks=NetworkRegistry({'lab-applications-011':context['network']},cluster_uuid=request['cluster_uuid'],node='proxmox')
    node.tls_factory=InstanceTLS.from_node
    node.isolation_factory=lambda:IsolationManager(directory=Path('/var/lib/nap-application-isolation'),
        boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())
    def execute(argv,**kwargs):
        if argv[0]=='/usr/bin/systemd-run':
            if argv[-1]!=request['execution_id'] or argv[-2]!='/opt/nap/applications/job/worker.py':raise JobError('UNCONFIRMED')
            # Same fixed production properties, separate root-only pending gate.
            argv=[*argv[:-2],str(Path(__file__).resolve()),'--worker',request['execution_id']]
        return bounded_command(argv,**kwargs)
    store=StateStore('/var/lib/nap-application-jobs',create=False)
    channel=CredentialChannel(create=False)
    supervisor=Supervisor(store=store,profiles=profiles,service=SystemdService(run_command=execute),credentials=channel,
        assert_owner=node.assert_owner,cluster_uuid=request['cluster_uuid'],node='proxmox',platform=node.platform())
    return NodeRuntime(supervisor=supervisor,credentials=channel,strategies=StrategyLoader(),node=node)


def start(context):
    if context['create_requested']:raise ValueError('CREATE_ALREADY_REQUESTED_OBSERVE_ONLY')
    node='proxmox';slot=context['slot']
    if any(v['vmid']==VMID for v in pve('/cluster/resources',type='vm')):raise ValueError('VMID_BUSY')
    if any(p.get('poolid')==POOL for p in pve('/pools')):raise ValueError('POOL_ALREADY_EXISTS')
    call(['/usr/bin/pvesh','create','/pools','--poolid',POOL,'--comment','NAP011 final gate '+context['request']['resource_uuid']])
    context['create_requested']=True;context['phase']='create_requested';save(context)
    call(['/usr/sbin/pct','create',str(VMID),context['profile']['base']['volumen_lxc'],
        '--hostname','nap011-final-'+UUID(context['request']['resource_uuid']).hex[:10],
        '--description',json.dumps(config_marker(context)),'--rootfs','local-lvm:8','--memory','1024','--swap','0',
        '--cores','2','--unprivileged','1','--start','0','--onboot','0','--pool',POOL,'--nameserver','172.16.36.2',
        '--net0','name=eth0,bridge=vmbr0,hwaddr='+slot['mac_address']+',ip='+slot['address']+'/24,gw=172.16.36.2,firewall=1'],timeout=180)
    owned(context)
    context['job_requested']=True;context['phase']='job_requested';save(context)
    with runtime(context) as engine:
        request={**context['request'],'secretos':{'APP_PRIVATE_VALUE':secrets.token_urlsafe(40)}}
        response=engine.supervisor.handle(encode(request))
        if not response.get('ok'):raise ValueError('JOB_NOT_CONFIRMED')
        return {'state':response['data']['estado'],'phase':response['data']['fase'],'vmid':VMID,'profiles_enabled':False}


def status(context):
    with runtime(context) as engine:
        job=engine.supervisor.store.read_job(context['request']['execution_id'])
        state={'gate_phase':context['phase'],'vmid':VMID,'profiles_enabled':False,
            'guest_exists':owned(context)is not None,'job_state':job['estado'] if job else None,
            'job_phase':job['fase'] if job else None,'error_code':job['error_codigo'] if job else None,
            'result':job['resultado'] if job else None,'last_source_seq':job['last_source_seq'] if job else 0}
        return state


def worker(context,execution):
    if execution!=context['request']['execution_id']:raise ValueError('WRONG_EXECUTION')
    assets()
    from applications.job.worker import ApplicationWorker
    with runtime(context) as engine:
        return ApplicationWorker(supervisor=engine.supervisor,credentials=engine.credentials,strategies=engine.strategies,
            emit=engine.emitter(execution),node=engine.node).run(execution,invocation_id=str(UUID(os.environ['INVOCATION_ID'])))


def cleanup(context):
    assets()
    from applications.job.state import StateStore
    from applications.job.supervisor import SystemdService
    from node_executor import bounded_command
    from applications.job.isolation import normalized
    request=context['request'];execution=request['execution_id']
    with StateStore('/var/lib/nap-application-jobs',create=False) as store:
        job=store.read_job(execution)
        if job is not None and job['identity']['resource_uuid']!=request['resource_uuid']:raise ValueError('FOREIGN_JOB')
        service=SystemdService(run_command=bounded_command)
        unit=service.observe(execution)
        if unit['state'] in {'active','starting'}:
            if job is None:raise ValueError('UNOWNED_UNIT')
            call(['/usr/bin/systemctl','stop',service.unit(execution)],timeout=20)
            if service.observe(execution)['state'] in {'active','starting'}:raise ValueError('UNIT_STILL_ACTIVE')
    config=owned(context)
    if config is not None:
        state=pve('/nodes/proxmox/lxc/'+str(VMID)+'/status/current')
        if state['status']!='stopped':call(['/usr/sbin/pct','stop',str(VMID)],timeout=45)
        owned(context)
        call(['/usr/sbin/pct','destroy',str(VMID),'--purge','1','--destroy-unreferenced-disks','0'],timeout=90)
    if owned(context) is not None or pve('/nodes/proxmox/storage/local-lvm/content',vmid=VMID):raise ValueError('ABSENCE_NOT_CONFIRMED')
    table='nap011_'+UUID(request['resource_uuid']).hex
    rules=bounded_command(['/usr/sbin/nft','-j','list','tables'],timeout=5,limit=2097152)
    if any(v.get('table',{}).get('name')==table for v in json.loads(rules)['nftables']):
        with StateStore('/var/lib/nap-application-isolation',create=False) as store:
            receipt=store.read('credential',request['resource_uuid'])
        if not receipt or receipt['binding']['nonce_sha256']!=sha256(request['nonce'].encode()).hexdigest():raise ValueError('UNOWNED_TABLE')
        actual=json.loads(bounded_command(['/usr/sbin/nft','-j','list','table','bridge',table],timeout=5,limit=2097152))
        if receipt['state']!='applied' or sha256(encode(normalized(actual))).hexdigest()!=receipt['nft_sha256']:raise ValueError('CHANGED_TABLE')
        call(['/usr/sbin/nft','delete','table','bridge',table])
    pools=[p for p in pve('/pools') if p.get('poolid')==POOL]
    if pools:
        detail=pve('/pools/'+POOL)
        if detail.get('comment')!='NAP011 final gate '+request['resource_uuid'] or detail.get('members'):raise ValueError('FOREIGN_POOL')
        call(['/usr/bin/pvesh','delete','/pools/'+POOL])
    context['phase']='cleaned';save(context)
    return {'state':'cleaned','guest_absent':True,'disks_absent':True,'vmid':VMID,'profiles_enabled':False}


def main():
    if os.geteuid()!=0:raise SystemExit(1)
    os.umask(0o077);BASE.mkdir(mode=0o700,exist_ok=True)
    parser=argparse.ArgumentParser();parser.add_argument('--init',action='store_true');parser.add_argument('--start',action='store_true')
    parser.add_argument('--status',action='store_true');parser.add_argument('--worker');parser.add_argument('--cleanup',action='store_true')
    args=parser.parse_args()
    try:
        if args.init:
            raw=sys.stdin.buffer.read(1048577)
            if len(raw)>1048576:raise ValueError()
            result=initialize(json.loads(raw))
        else:
            context=load()
            if args.worker:return worker(context,args.worker)
            result=cleanup(context) if args.cleanup else start(context) if args.start else status(context)
        print(json.dumps(result));return 0
    except Exception as exc:
        print(json.dumps({'state':'not_confirmed','error_type':type(exc).__name__}));return 1


if __name__=='__main__':raise SystemExit(main())
