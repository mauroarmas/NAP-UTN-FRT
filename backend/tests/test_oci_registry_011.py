"""OCI metadata only; no docker daemon, downloads of layers or deployments."""
from hashlib import sha256
import json

from fastapi import HTTPException
import httpx
import pytest

from app.services.oci_registry_service import Resolver,reference,digest,IMAGE_TYPES,INDEX_TYPES,CONFIG_TYPES,LAYER_TYPES

IMAGE=sorted(IMAGE_TYPES)[0];INDEX=sorted(INDEX_TYPES)[0];CONFIG=sorted(CONFIG_TYPES)[0];LAYER=sorted(LAYER_TYPES)[0]


def encoded(value):return json.dumps(value,separators=(',',':')).encode()
def desc(raw,media):return {'mediaType':media,'digest':digest(raw),'size':len(raw)}


@pytest.fixture
def image():
    config=encoded({'os':'linux','architecture':'amd64','rootfs':{'type':'layers','diff_ids':['sha256:'+'1'*64]},
        'config':{'Entrypoint':['/own/entrypoint'],'Cmd':['own-argument'],'Volumes':{'/data':{}}}})
    manifest=encoded({'schemaVersion':2,'mediaType':IMAGE,'config':desc(config,CONFIG),
        'layers':[{'mediaType':LAYER,'digest':'sha256:'+'2'*64,'size':1234}]})
    index=encoded({'schemaVersion':2,'mediaType':INDEX,'manifests':[{**desc(manifest,IMAGE),'platform':{'os':'linux','architecture':'amd64'}}]})
    return {'config':config,'manifest':manifest,'index':index}


@pytest.fixture
def registry(image):
    calls=[];state={'index':True,'failure':None,'token':False}
    profile={'registry':{'host':'registry.example.edu','addresses':['10.20.0.10']},
        'reference_hosts':['registry.example.edu'],'repository_prefixes':['campus/'],
        'token_endpoint':{'host':'auth.example.edu','addresses':['10.20.0.11']},'token_service':'campus-registry'}
    async def lookup(host,port):return ['10.20.0.11' if host=='auth.example.edu' else '10.20.0.10']
    def handler(request):
        calls.append(request)
        if request.headers['host']=='auth.example.edu':
            assert request.url.params['scope']=='repository:campus/demo:pull'
            return httpx.Response(200,content=encoded({'token':'fixture.private.token'}))
        if state['token'] and request.headers.get('authorization')!='Bearer fixture.private.token':
            realm='https://evil.example/token' if state['failure']=='realm' else 'https://auth.example.edu/token'
            return httpx.Response(401,headers={'www-authenticate':'Bearer realm="'+realm+'",service="campus-registry",scope="repository:campus/demo:pull"'})
        if state['failure']=='redirect':return httpx.Response(307,headers={'location':'https://evil.example/x'})
        path=request.url.path
        if '/blobs/' in path:raw=image['config']
        elif path.endswith('release'):raw=image['index'] if state['index'] else image['manifest']
        else:raw=image['manifest']
        if state['failure']=='digest' and '/blobs/' in path:raw=raw+b' '
        return httpx.Response(200,headers={'docker-content-digest':digest(raw)},content=raw)
    def factory(**kwargs):
        assert kwargs['trust_env'] is False and kwargs['retries']==0
        return httpx.MockTransport(handler)
    resolver=Resolver(profile,transport_factory=factory,lookup=lookup)
    return resolver,calls,state,image


async def test_index_manifest_and_config_are_distinct_and_tag_is_frozen_without_execution(registry):
    resolver,calls,state,image=registry
    result=await resolver.resolve('registry.example.edu/campus/demo:release',architecture='amd64')
    assert result['manifest_digest']==digest(image['manifest']) and result['index_digest']==digest(image['index'])
    assert result['config_digest']==digest(image['config']) and len({result['manifest_digest'],result['index_digest'],result['config_digest']})==3
    assert result['volumes']==['/data'] and len(calls)==3
    assert calls[1].url.path.endswith(result['manifest_digest'])
    assert all(c.url.host=='10.20.0.10' and c.extensions['sni_hostname']=='registry.example.edu' for c in calls)
    assert not any('/layers/' in c.url.path for c in calls)
    assert 'Entrypoint' not in result and 'own-argument' not in repr(result)


async def test_single_manifest_and_explicit_digest_are_checked(registry):
    resolver,calls,state,image=registry;state['index']=False
    result=await resolver.resolve('registry.example.edu/campus/demo@'+digest(image['manifest']),architecture='amd64')
    assert result['index_digest'] is None and result['tag_original'] is None
    assert len(calls)==2


@pytest.mark.parametrize('failure',['digest','redirect','realm','architecture','volume','foreign-layer'])
async def test_malicious_or_incompatible_metadata_never_resolves(registry,failure):
    resolver,calls,state,image=registry
    if failure in {'digest','redirect','realm'}:state['failure']=failure
    if failure=='realm':state['token']=True
    if failure=='architecture':
        value=json.loads(image['index']);value['manifests'][0]['platform']['architecture']='arm64';image['index']=encoded(value)
    if failure=='volume':
        config=json.loads(image['config']);config['config']['Volumes']={'/var/run':{}};image['config']=encoded(config)
        manifest=json.loads(image['manifest']);manifest['config']=desc(image['config'],CONFIG);image['manifest']=encoded(manifest);state['index']=False
    if failure=='foreign-layer':
        manifest=json.loads(image['manifest']);manifest['layers'][0]['urls']=['http://169.254.169.254/credentials'];image['manifest']=encoded(manifest);state['index']=False
    with pytest.raises(HTTPException) as caught:await resolver.resolve('registry.example.edu/campus/demo:release',architecture='amd64')
    assert caught.value.status_code==502 and 'fixture.private.token' not in str(caught.value)
    assert not any(c.headers['host']=='evil.example' for c in calls)


async def test_private_bearer_uses_only_fixed_auth_server_scope_and_no_credentials_in_registry(registry):
    resolver,calls,state,image=registry;state['token']=True
    resolver.credentials=lambda:{'username':'fixture-reader','password':'fixture-private-password'}
    result=await resolver.resolve('registry.example.edu/campus/demo:release',architecture='amd64')
    assert result['manifest_digest']==digest(image['manifest'])
    auth=[c for c in calls if c.headers['host']=='auth.example.edu']
    assert len(auth)==1 and auth[0].headers['authorization'].startswith('Basic ')
    assert all('fixture-private-password' not in str(c.url) for c in calls)
    assert all(not c.headers.get('authorization','').startswith('Basic ') for c in calls if c.headers['host']=='registry.example.edu')
    assert resolver.authorization is None


async def test_dns_rebinding_or_management_ip_is_rejected_before_any_request(registry):
    resolver,calls,state,image=registry
    async def poisoned(host,port):return ['10.20.0.10','127.0.0.1']
    resolver.lookup=poisoned
    with pytest.raises(HTTPException):await resolver.resolve('registry.example.edu/campus/demo:release',architecture='amd64')
    assert not calls


@pytest.mark.parametrize('value',['https://example.edu/image','user:password@registry.example.edu/repo',
    'example.edu/image@sha256:bad','../escape','nginx; rm -rf /','localhost:5443/../image'])
def test_reference_rejects_urls_credentials_commands_and_traversal(value):
    with pytest.raises(HTTPException):reference(value)


def test_familiar_docker_reference_is_normalized_without_asking_for_registry_codes():
    assert reference('nginx:1.27')==('docker.io','library/nginx','1.27')
    assert reference('university/course:2026')==('docker.io','university/course','2026')


@pytest.mark.parametrize('failure',['none','foreign','second-redirect','content'])
async def test_only_registered_blob_cdn_is_followed_without_auth_or_signed_url_logs(registry,caplog,failure):
    from app.schemas.oci_registry import Endpoint
    resolver,calls,state,image=registry
    resolver.profile.blob_endpoints=[Endpoint(host='cdn.example.edu',addresses=['10.20.0.12'])]
    original=resolver.transport_factory
    async def lookup(host,port):return ['10.20.0.12' if host=='cdn.example.edu' else '10.20.0.10']
    resolver.lookup=lookup
    def handler(request):
        calls.append(request)
        if request.headers['host']=='cdn.example.edu':
            assert 'authorization' not in request.headers and 'cookie' not in request.headers
            if failure=='second-redirect':return httpx.Response(307,headers={'location':'https://evil.example/'})
            return httpx.Response(200,content=image['config']+(b'bad' if failure=='content' else b''))
        if '/blobs/' in request.url.path:
            return httpx.Response(307,headers={'location':'https://'+('evil.example' if failure=='foreign' else 'cdn.example.edu')+'/config?signature=fixture-signed-secret'})
        raw=image['index'] if request.url.path.endswith('release') else image['manifest']
        return httpx.Response(200,content=raw)
    resolver.transport_factory=lambda **kwargs:httpx.MockTransport(handler)
    if failure=='none':
        result=await resolver.resolve('registry.example.edu/campus/demo:release',architecture='amd64')
        assert result['config_digest']==digest(image['config'])
    else:
        with pytest.raises(HTTPException):await resolver.resolve('registry.example.edu/campus/demo:release',architecture='amd64')
    assert 'fixture-signed-secret' not in caplog.text
    assert not any(c.headers['host']=='evil.example' for c in calls)


async def test_private_ca_is_not_silently_disabled_when_missing(registry):
    resolver,calls,state,image=registry
    resolver.profile.registry.ca_file='/missing/fixture-private-ca.crt'
    with pytest.raises(HTTPException) as caught:await resolver.resolve('registry.example.edu/campus/demo:release',architecture='amd64')
    assert not calls and '/missing/' not in str(caught.value)


async def test_metadata_body_is_bounded_before_json_parsing(registry):
    resolver,calls,state,image=registry
    image['index']=b'x'*(8388608+1)
    with pytest.raises(HTTPException):await resolver.resolve('registry.example.edu/campus/demo:release',architecture='amd64')
    assert len(calls)==1


@pytest.mark.parametrize('bad',['world-readable','link','hardlink'])
def test_private_registry_credentials_cannot_come_from_public_or_linked_files(tmp_path,bad):
    import os
    from app.services.oci_registry_service import read_credentials
    folder=tmp_path/'private';folder.mkdir(mode=0o700)
    path=folder/'credentials.json';path.write_text('{"username":"fixture","password":"private-test"}');path.chmod(0o600)
    assert read_credentials(path)['username']=='fixture'
    if bad=='world-readable':path.chmod(0o644)
    if bad=='link':
        original=folder/'original.json';path.rename(original);path.symlink_to(original)
    if bad=='hardlink':os.link(path,folder/'second.json')
    with pytest.raises(ValueError):read_credentials(path)


async def test_tag_change_does_not_rewrite_previously_resolved_digests(registry):
    resolver,calls,state,image=registry
    first=await resolver.resolve('registry.example.edu/campus/demo:release',architecture='amd64')
    original=first.copy()
    config=json.loads(image['config']);config['config']['Cmd']=['new-command'];image['config']=encoded(config)
    manifest=json.loads(image['manifest']);manifest['config']=desc(image['config'],CONFIG);image['manifest']=encoded(manifest)
    index=json.loads(image['index']);index['manifests'][0].update(desc(image['manifest'],IMAGE));image['index']=encoded(index)
    second=await resolver.resolve('registry.example.edu/campus/demo:release',architecture='amd64')
    assert second['manifest_digest']!=first['manifest_digest'] and first==original
