from copy import deepcopy
import hashlib,json
from pathlib import Path
from uuid import uuid4
import pytest
from infra.builder import actions
from tests.drawio_helpers import drawio_manifest
from app.schemas.definicion import digest
from app.utils.artifact_registry import entry_name,read_private_json


@pytest.mark.parametrize('replica_local',[False,True])
def test_resolve_build_stage_recargable_y_no_altera_paquete(tmp_path,monkeypatch,replica_local):
    manifest=drawio_manifest();manifest.pop('validation')
    plan={'schema_version':1,'definition_id':str(uuid4()),'base_sha256':'c'*64,'source_date_epoch':1700000000,'package_lock':{'base':'1.0'},'manifest':manifest}
    planpath=tmp_path/'plan.json';planpath.write_text(actions.canonical(plan));planpath.chmod(0o444)
    directories={name:tmp_path/name for name in ['images','bundles','runner','portal']}
    for directory in directories.values():directory.mkdir(mode=0o755);directory.chmod(0o755)
    target={'node':'pve1','storage_id':'local','cluster_uuid':str(uuid4()),'networks':{},'nodes':['pve1'],'network_profile_id':'test-network',
        'image_directory':str(directories['images']),'bundle_directory':str(directories['bundles']),
        'portal_image_path':'/mnt/image','portal_bundle_path':'/mnt/bundle','runner_registry_directory':str(directories['runner']),'portal_registry_directory':str(directories['portal'])}
    if replica_local:
        for name in ['portal_images','portal_bundles']:
            directories[name]=tmp_path/name;directories[name].mkdir(mode=0o755)
        target.update(portal_image_directory=str(directories['portal_images']),portal_bundle_directory=str(directories['portal_bundles']))
    config={'recipe':actions.RECIPE,'revision':'a'*40,'input_ref':'approved','plan_path':str(planpath),'base_path':str(tmp_path/'base'),'base_sha256':'c'*64,'targets':[target]}
    (tmp_path/'registry.json').write_text(actions.canonical(config));(tmp_path/'registry.json').chmod(0o600)
    request={'action':'resolve','ensayo_id':str(uuid4()),'operation_id':'resolve','recipe_id':actions.RECIPE,'recipe_revision':'a'*40,'input_ref':'approved',
        'input_sha256':hashlib.sha256(actions.canonical(plan).encode()).hexdigest(),'definition_id':str(uuid4()),'definition_key':'drawio-trial','definition_version':'1.0.0'}
    resolved=actions.execute_registered(request,tmp_path)
    assert resolved['entradas_resueltas']['definition_id']==request['definition_id']
    calls=[]
    def fake_build(plan,base,output):
        calls.append(plan);output.mkdir();value=deepcopy(plan['manifest'])
        image=output/value['image']['volume_id'].split('/')[-1];image.write_bytes(b'image')
        bundle=output/'recipe.tar.gz';bundle.write_bytes(b'bundle')
        value['image']['sha256']=hashlib.sha256(image.read_bytes()).hexdigest();value['preparation']['bundle_sha256']=hashlib.sha256(bundle.read_bytes()).hexdigest()
        (output/'manifest-draft.json').write_text(actions.canonical(value));(output/'manifest-draft.json').chmod(0o444)
        return {'manifest':value,'image_path':str(image),'bundle_path':str(bundle)}
    monkeypatch.setattr(actions,'build_artifact',fake_build)
    built_request=request|{'action':'build','operation_id':'build','input_ref':resolved['input_ref'],'input_sha256':resolved['input_sha256']}
    built=actions.execute_registered(built_request,tmp_path)
    assert built['manifest']['image']['volume_id']=='local:vztmpl/nap-drawio-trial-1.0.0.tar.gz'
    assert actions.execute_registered(built_request|{'operation_id':'retry'},tmp_path)==built and len(calls)==1
    staged=actions.execute_registered(built_request|{'action':'stage','operation_id':'stage'},tmp_path)
    key='drawio-trial:1.0.0';document=read_private_json(directories['portal']/entry_name(key))
    assert document['portal']['registry_revision']==digest(built['manifest'])
    assert staged['replicas'][0]['image_sha256']==built['manifest']['image']['sha256']
    if replica_local:
        assert Path(document['portal']['image_path']).read_bytes()==b'image'
        assert Path(document['portal']['bundle_path']).read_bytes()==b'bundle'
    invalid=deepcopy(built['manifest']);invalid['validation']=drawio_manifest()['validation'];invalid['minimum_resources']['vcpus']=99
    with pytest.raises(ValueError):actions.execute_registered(built_request|{'action':'stage','operation_id':'bad','validated_manifest':invalid},tmp_path)
