"""Acciones permitidas; el registro privado define entradas y montajes de destino."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
from app.utils.artifact_registry import read_private_json,entry_name
from app.schemas.definicion import validar_manifest,digest
from infra.services.build_image import build_artifact,file_sha256
from infra.laboratorio.instalar_artefactos import copy_exclusive,secure_path

RECIPE='drawio-tomcat11-ubuntu-24.04-v1'


def registry(root):
    value=read_private_json(Path(root)/'registry.json',limit=1048576)
    if set(value)!={'recipe','revision','input_ref','plan_path','base_path','base_sha256','targets'} or value['recipe']!=RECIPE:
        raise ValueError('Registro de construcción inválido')
    if not re.fullmatch('[a-f0-9]{40}',value['revision']):raise ValueError('Revisión no fijada')
    return value


def profile(root):
    try:
        value=registry(root)
        plan=read_private_json(value['plan_path'],limit=1048576)
        if file_sha256(value['base_path'])!=value['base_sha256']:raise ValueError('Base alterada')
        from infra.services.build_image import verify_recipe_revision
        verify_recipe_revision(value['revision'],'drawio')
        return {'recipe_ready':True,'recipe_revision':value['revision'],'input_ref':value['input_ref'],
            'input_sha256':hashlib.sha256(canonical(plan).encode()).hexdigest()}
    except Exception:return {'recipe_ready':False}


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)


def write_exclusive(path,value):
    raw=canonical(value).encode();path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    try:
        fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o444)
    except FileExistsError:
        if read_private_json(path,limit=1048576)!=value:raise ValueError('Contenido diferente')
        return
    with os.fdopen(fd,'wb') as handle:handle.write(raw);handle.flush();os.fsync(handle.fileno())


def execute_registered(request,root):
    root=Path(root);config=registry(root)
    if request['recipe_id']!=RECIPE or request['recipe_revision']!=config['revision']:raise ValueError('Receta no permitida')
    work=root/'work'/request['ensayo_id'];work.mkdir(parents=True,exist_ok=True,mode=0o700)
    if work.resolve()!=work:raise ValueError('Workspace no controlado')
    if request['action']=='resolve':
        if request['input_ref']!=config['input_ref']:raise ValueError('Inputs no registrados')
        plan=read_private_json(config['plan_path'],limit=1048576)
        if hashlib.sha256(canonical(plan).encode()).hexdigest()!=request['input_sha256']:raise ValueError('Inputs alterados')
        plan=deepcopy(plan)
        plan['definition_id']=request['definition_id']
        plan['manifest']['definition_key']=request['definition_key']
        plan['manifest']['definition_version']=request['definition_version']
        storage=plan['manifest']['image']['volume_id'].split(':',1)[0]
        plan['manifest']['image']['volume_id']=f"{storage}:vztmpl/nap-{request['definition_key']}-{request['definition_version']}.tar.gz"
        plan['manifest']['preparation']['recipe_revision']=config['revision']
        validar_manifest(plan['manifest'],parcial=True)
        checksum=hashlib.sha256(canonical(plan).encode()).hexdigest()
        write_exclusive(root/'inputs'/(checksum+'.json'),plan)
        return {'input_ref':checksum,'input_sha256':checksum,'entradas_resueltas':{
            'base_sha256':plan['base_sha256'],'package_lock':plan['package_lock'],'runtime':plan['manifest']['runtime'],
            'recipe_revision':config['revision'],'definition_id':plan['definition_id'],
            'definition_key':plan['manifest']['definition_key'],'definition_version':plan['manifest']['definition_version']}}
    if not re.fullmatch('[a-f0-9]{64}',request['input_ref']):raise ValueError('Inputs no resueltos')
    plan=read_private_json(root/'inputs'/(request['input_ref']+'.json'),limit=1048576)
    if hashlib.sha256(canonical(plan).encode()).hexdigest()!=request['input_sha256']:raise ValueError('Inputs alterados')
    output=root/'artifacts'/request['ensayo_id']
    output.parent.mkdir(parents=True,exist_ok=True,mode=0o755)
    if request['action']=='build':
        if output.exists():
            result=read_private_json(output/'build-result.json',limit=1048576)
            manifest=result['manifest']
            if (file_sha256(output/manifest['image']['volume_id'].split('/')[-1])!=manifest['image']['sha256']
                or file_sha256(output/'recipe.tar.gz')!=manifest['preparation']['bundle_sha256']):raise ValueError('Artefacto retenido alterado')
            return result
        temporary=work/('build-'+request['operation_id'])
        built=build_artifact(plan,config['base_path'],temporary)
        result={'artifact_ref':request['ensayo_id'],'manifest':built['manifest'],
            'image_bytes':Path(built['image_path']).stat().st_size,'bundle_bytes':Path(built['bundle_path']).stat().st_size,
            'saneamiento':{'builder_sanitized':True}}
        write_exclusive(temporary/'build-result.json',result)
        os.rename(temporary,output)
        return result
    if request['action']!='stage':raise ValueError('Acción no permitida')
    manifest=read_private_json(output/'manifest-draft.json')
    expected=request.get('validated_manifest')
    if expected is not None:
        validar_manifest(expected)
        if {k:v for k,v in expected.items() if k!='validation'}!={k:v for k,v in manifest.items() if k!='validation'}:
            raise ValueError('La validación cambia el artefacto')
        manifest=expected
    image=output/manifest['image']['volume_id'].split('/')[-1];bundle=output/'recipe.tar.gz'
    key=manifest['definition_key']+':'+manifest['definition_version']
    replicas=[]
    # Targets son montajes institucionales preconfigurados por nodo. Sin shell/SSH libre.
    for target in config['targets']:
        node=target['node'];storage=target['storage_id']
        image_target=secure_path(target['image_directory'])/image.name
        bundle_target=secure_path(target['bundle_directory'])/(manifest['preparation']['bundle_sha256']+'.tar.gz')
        for source,destination,checksum in [(image,image_target,manifest['image']['sha256']),(bundle,bundle_target,manifest['preparation']['bundle_sha256'])]:
            if destination.exists():
                if file_sha256(destination)!=checksum:raise ValueError('Réplica distinta')
            else:copy_exclusive({'source':source,'target':destination,'sha256':checksum,'size':source.stat().st_size})
        portal_image=target.get('portal_image_path')
        portal_bundle=target.get('portal_bundle_path')
        # Un preparador separado puede conservar una réplica local de lectura para el portal.
        if 'portal_image_directory' in target or 'portal_bundle_directory' in target:
            portal_image=secure_path(target['portal_image_directory'])/image.name
            portal_bundle=secure_path(target['portal_bundle_directory'])/(manifest['preparation']['bundle_sha256']+'.tar.gz')
            for source,destination,checksum in [(image,portal_image,manifest['image']['sha256']),(bundle,portal_bundle,manifest['preparation']['bundle_sha256'])]:
                if destination.exists():
                    if file_sha256(destination)!=checksum:raise ValueError('Réplica local distinta')
                else:copy_exclusive({'source':source,'target':destination,'sha256':checksum,'size':source.stat().st_size})
        runner={'product':'drawio','definition_sha256':digest(manifest),'bundle_sha256':manifest['preparation']['bundle_sha256'],
            'bundle_path':str(bundle_target),'cluster_uuid':target['cluster_uuid'],'nodes':[node],
            'network_profile_ids':manifest['network_profile_ids'],'networks':target['networks']}
        portal={'definition_sha256':digest(manifest),'image_path':str(portal_image),'bundle_path':str(portal_bundle),
            'nodes':target['nodes'],'network_profile_id':target['network_profile_id'],'registry_revision':digest(manifest)}
        document={'key':key,'runner':runner,'portal':portal}
        # Actualización de digest draft→validado permitida sólo por la misma imagen/bundle.
        for directory in [target['runner_registry_directory'],target['portal_registry_directory']]:
            parent=secure_path(directory);path=parent/entry_name(key)
            if path.exists():
                old=read_private_json(path)
                if old['portal']['image_path']!=portal['image_path'] or old['runner']['bundle_sha256']!=runner['bundle_sha256']:
                    raise ValueError('No sustituir otro artefacto')
            temp=parent/(entry_name(key)+'.tmp')
            fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o444)
            with os.fdopen(fd,'w') as handle:handle.write(canonical(document));handle.flush();os.fsync(handle.fileno())
            os.replace(temp,path)
        replicas.append({'nodo':node,'storage_id':storage,'image_sha256':manifest['image']['sha256'],
            'bundle_sha256':manifest['preparation']['bundle_sha256'],'registro_revision':digest(manifest)})
    if not replicas:raise ValueError('Sin destinos de réplica')
    return {'replicas':replicas,'manifest_sha256':digest(manifest)}
