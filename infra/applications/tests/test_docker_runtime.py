"""Fixed strategy and guest CLI tests. No Docker/PVE effects are certified here."""
from copy import deepcopy
from hashlib import sha256
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from infra.applications.docker.runtime import policy,policy_digest,validate_profile,application_arguments,volume_name
from infra.applications.docker.guest import DockerGuest,InstallError
from infra.applications.docker import deploy as strategy
from infra.applications.job.protocol import canonical,JobError
from infra.applications.tests.test_job_supervisor import rig


@pytest.fixture
def application(rig,profile_entry):
    lock=policy();profile=deepcopy(profile_entry['definition'])
    profile.update(base=lock['base'],runtime={**lock['packages'],'storage_driver':lock['storage_driver']},
        minimum_resources=lock['minimum_resources'],policy_bundle_sha256=policy_digest())
    configuration=deepcopy(rig.request['configuracion']);configuration['base']=lock['base']
    identity={key:value for key,value in rig.request.items() if key in ('resource_uuid','cluster_uuid','vmid','configuracion_sha256')}
    identity['nonce_sha256']='a'*64
    return SimpleNamespace(profile=profile,configuration=configuration,identity=identity,lock=lock)


def test_application_plan_preserves_command_and_uses_digest_scoped_volumes_and_names(application):
    app=application;args=application_arguments(app.identity,app.configuration,{'vcpus':2,'ram_mb':1024,'disk_gb':8})
    assert args[-1]==app.configuration['imagen']['repositorio']+'@'+app.configuration['imagen']['manifest_digest']
    assert '--entrypoint' not in args and '--privileged' not in args
    assert '--log-driver=none'in args and '--no-healthcheck'in args and '--cap-drop=ALL'in args
    assert '--publish=127.0.0.1:18080:8080'in args and '--pull=never'in args
    assert 'APP_PASSWORD'in args and 'fixture-private-password-011'not in repr(args)
    assert any('source='+volume_name(app.identity['resource_uuid'],'/data')+',target=/data'in v for v in args)
    other={**app.identity,'resource_uuid':str(uuid4())}
    assert volume_name(other['resource_uuid'],'/data')!=volume_name(app.identity['resource_uuid'],'/data')
    with pytest.raises(ValueError):application_arguments(app.identity,app.configuration,{'vcpus':2,'ram_mb':2048,'disk_gb':8})


def test_profile_is_bound_to_exact_runtime_and_current_code_bundle(application):
    assert validate_profile(application.profile)==application.lock
    for field in ('base','runtime','policy_bundle_sha256'):
        changed=deepcopy(application.profile)
        if field=='base':changed['base']['sha256']='0'*64
        if field=='runtime':changed['runtime']['docker']='latest'
        if field=='policy_bundle_sha256':changed[field]='0'*64
        with pytest.raises(JobError):validate_profile(changed)


@pytest.mark.parametrize('failure',[None,'pull','probe'])
def test_one_guest_strategy_has_real_stages_and_never_passes_pull_auth_to_application(application,monkeypatch,failure):
    app=application;events=[];commands=[];phase=[];sensitive=[]
    class Node:
        def _configuration(self,owner):return {'cores':2,'memory':1024},app.profile
        def start_guest(self,owner):events.append('guest-start')
        def bootstrap_docker(self,*args):events.append('bootstrap')
        def assert_confinement(self,owner):events.append('confinement')
        def docker_action(self,owner,action,payload,context):
            events.append(action);commands.append((action,deepcopy(payload)))
            if action==failure:raise JobError('DEPENDENCY_UNAVAILABLE')
            return {'ok':True}
    context=SimpleNamespace(node=Node(),identity=app.identity,configuration=app.configuration,network={'host':'app81.nap.test'},
        tls={'private_key_pem':'fixture-TLS-key','certificate_pem':'fixture-cert','ca_pem':'fixture-CA'},
        phase=phase.append,begin_output=lambda **kwargs:sensitive.extend(kwargs.get('extra_secrets',[])),
        secret=lambda name:'fixture-app-private\nmultiline')
    monkeypatch.setattr(strategy,'registry_credentials',lambda image:{'reference_host':'registry.example.edu',
        'username':'fixture-reader','password':'fixture-pull-private','ca_pem':'fixture-CA'})
    if failure:
        with pytest.raises(JobError):strategy.deploy(context)
        assert events[-1]==failure
        if failure=='pull':assert 'start'not in events and 'configure'not in events
    else:
        result=strategy.deploy(context)
        assert result['recurso_configurado'] and set(result['comprobaciones'])=={'runtime','aislamiento','salud','acceso_web'}
        assert phase==['instalacion','configuracion','arranque','comprobacion']
    for action,payload in commands:
        assert ('registry'in payload)==(action=='pull')
        assert ('private_values'in payload)==(action=='start')
        if action=='probe':assert set(payload['tls'])=={'ca_pem'}
    assert 'fixture-pull-private'in sensitive


def test_guest_launch_keeps_multiline_secret_in_process_environment_not_argv(application,tmp_path):
    app=application;calls=[];private='fixture-private\nsecond-line'
    request={'identity':app.identity,'configuration':app.configuration,'resources':{'vcpus':2,'ram_mb':1024,'disk_gb':8},
        'edge':app.lock['edge'],'private_values':{'APP_PASSWORD':private},'action':'start'}
    mounts=[{'Destination':p,'Type':'volume','Name':volume_name(app.identity['resource_uuid'],p)} for p in app.configuration['persistencia']]
    def run(args,**kwargs):
        calls.append((args,kwargs))
        if 'inspect'in args:
            return json.dumps([{'State':{'Running':True},'Image':app.configuration['imagen']['config_digest'],
                'Config':{'Labels':{'nap.resource_uuid':app.identity['resource_uuid']},'Healthcheck':{'Test':['NONE']}},
                'HostConfig':{'LogConfig':{'Type':'none'}},'AppArmorProfile':'docker-default','Mounts':mounts}]).encode()
        return b''
    guest=DockerGuest(request,root=tmp_path,run=run);guest.execute()
    app_run=next(v for v in calls if '--network=bridge'in v[0])
    assert app_run[1]['environment']['APP_PASSWORD']==private
    assert all(private not in repr(args) for args,_ in calls)
    assert (tmp_path/'run/nap-docker-cli/config.json').read_text()=='{"auths":{}}'
    edge_run=next(v for v in calls if '--network=host'in v[0])
    assert edge_run[1]['environment'] is None and '--entrypoint=caddy'in edge_run[0]


def test_registry_authentication_is_private_ephemeral_and_removed_before_edge_pull(application,tmp_path):
    app=application;calls=[];root=tmp_path
    request={'identity':app.identity,'configuration':app.configuration,'edge':app.lock['edge'],'action':'pull',
        'registry':{'reference_host':app.configuration['imagen']['repositorio'].split('/')[0],
            'username':'fixture-reader','password':'fixture-pull-secret','ca_pem':None}}
    def run(args,**kwargs):
        calls.append(args)
        if 'pull'in args:
            selected=args[args.index('--config')+1]
            if args[-1].startswith(app.lock['edge']['repositorio']):
                assert not list((root/'run').glob('nap-pull-*'))
            else:
                path=__import__('pathlib').Path(selected)/'config.json'
                assert path.stat().st_mode&0o077==0 and 'auths'in json.loads(path.read_text())
        if 'inspect'in args:
            edge=args[-1].startswith(app.lock['edge']['repositorio'])
            return json.dumps([{'Id':app.lock['edge']['config_digest'] if edge else app.configuration['imagen']['config_digest'],
                'Os':'linux','Architecture':'amd64','Config':{'Volumes':{'/data':{}}}}]).encode()
        return b''
    guest=DockerGuest(request,root=root,run=run);guest.execute()
    assert not list((root/'run').glob('nap-pull-*'))
    assert all('fixture-pull-secret'not in repr(args) and 'fixture-reader'not in repr(args) for args in calls)


@pytest.mark.integration
def test_installed_readonly_package_has_same_policy_hash_without_backend_imports(tmp_path):
    from pathlib import Path
    import subprocess
    import sys
    from infra.applications.install import build_files,install_files
    source=Path(__file__).resolve().parents[3]
    node=tmp_path/'node';node.mkdir(mode=0o700)
    install_files(build_files(source),root=node,apply=True)
    code='import sys;sys.path.insert(0,sys.argv[1]);from applications.docker.runtime import policy_digest;print(policy_digest())'
    result=subprocess.run([sys.executable,'-I','-c',code,str(node/'opt/nap')],capture_output=True,timeout=10)
    assert result.returncode==0,result.stderr.decode()
    assert result.stdout.decode().strip()==policy_digest()
