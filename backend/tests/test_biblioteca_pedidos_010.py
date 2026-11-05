from copy import deepcopy
from uuid import uuid4
import hashlib
from sqlalchemy import select
from app.models.definicion_servicio import DefinicionServicio
from app.models.evidencia import Evidencia
from app.models.incorporacion_aplicacion import IncorporacionAplicacion
from app.models.recurso_template import RecursoTemplate,TipoRecurso
from app.models.pedido import ModeloServicio,Pedido
from app.schemas.definicion import digest
from app.schemas.evidencia import canonical
from app.utils.clock import clock
from tests.drawio_helpers import drawio_manifest
from tests.fakes_biblioteca import DRAWIO
from tests.service_helpers import definition_proof
from tests.test_perfiles_definiciones_009 import dates
from tests.capacity_helpers import perfil_capacidad


async def oferta(db,admin,*,version='1.0.0',inc=None,template=None,estado='publicada'):
    if inc is None:
        inc=IncorporacionAplicacion(**{k:DRAWIO[k] for k in ['identidad_externa','revision_fuente','comando_sha256','comando_origen','url_origen','nombre','descripcion','categorias','aliases']},origen_clave='fija',creado_por=admin.id)
        db.add(inc);await db.flush()
    value=drawio_manifest();value['definition_version']=version
    did=uuid4();eid=uuid4();proof=definition_proof(str(did),value);raw=canonical(proof);sha=hashlib.sha256(raw.encode()).hexdigest()
    db.add(Evidencia(id=eid,tipo='validacion_definicion',schema_version=1,documento_canonico=raw,sha256=sha,registrada_por=admin.id));await db.flush()
    value['validation'].update(evidence_id=str(eid),evidence_sha256=sha)
    definition=DefinicionServicio(id=did,codigo=value['definition_key'],version=version,producto='drawio',modelo_servicio='saas',
        incorporacion_id=inc.id,manifest=value,manifest_sha256=digest(value),estado=estado,validada_por=admin.id,validada_at=clock.now(),evidencia_validacion=eid)
    db.add(definition);await db.flush()
    if template is None:
        template=RecursoTemplate(nombre='Draw.io preparado',tipo=TipoRecurso.LXC,modelo_servicio=ModeloServicio.SAAS,default_vcpus=1,default_ram_mb=512,default_disk_gb=4,revision=1)
        db.add(template)
    else:template.revision+=1
    template.definicion_version_id=did;template.os_template=value['image']['volume_id'];await db.commit()
    return inc,definition,template


async def test_snapshot_original_y_evaluacion_version_vigente(client,db,admin,auth_admin,auth_catedra,catedra,perfil_capacidad,proxmox):
    inc,first,template=await oferta(db,admin)
    perfil_capacidad['cluster_id']=first.manifest['validation']['cluster_uuid']
    created=await client.post('/pedidos/',json={'template_id':template.id,'modelo_servicio':'saas','vigencia':dates()},headers=auth_catedra|{'Idempotency-Key':'pedido-bib'})
    assert created.status_code==201,created.text
    pedido_id=created.json()['id']
    assert created.json()['seleccion_oferta_snapshot']['version']=='1.0.0'
    _,second,template=await oferta(db,admin,version='2.0.0',inc=inc,template=template)
    # Fixture sintético: sólo evaluación y snapshots, nunca instalación real.
    perfil_capacidad['cluster_id']=second.manifest['validation']['cluster_uuid']
    proxmox.contenidos_storage[('pve1','local')]=[{'volid':second.manifest['image']['volume_id'],'content':'vztmpl'}]
    selection={'asignacion':{'template_id':template.id,'definicion_version_id':str(second.id),'vcpus':1,'ram_mb':512,'disk_gb':4},'vigencia':dates()}
    evaluated=await client.post(f'/pedidos/{pedido_id}/evaluacion',json=selection,headers=auth_admin)
    assert evaluated.status_code==200,evaluated.text
    assert evaluated.json()['cambio_version'] is True
    assert evaluated.json()['version_solicitada']=='1.0.0' and evaluated.json()['version_efectiva']=='2.0.0'
    approved=await client.post(f'/pedidos/{pedido_id}/aprobar',json=selection|{'capacidad_token':evaluated.json()['capacidad_token']},headers=auth_admin|{'Idempotency-Key':'aprobar-bib'})
    assert approved.status_code==200,approved.text
    pedido=await db.get(Pedido,pedido_id,populate_existing=True)
    assert pedido.seleccion_oferta_snapshot['version']=='1.0.0' and pedido.asignacion_snapshot['definition_version']=='2.0.0'
    frozen=deepcopy(pedido.asignacion_snapshot)
    replay=await client.post(f'/pedidos/{pedido_id}/aprobar',json=selection|{'capacidad_token':evaluated.json()['capacidad_token']},headers=auth_admin|{'Idempotency-Key':'aprobar-bib'})
    assert replay.status_code==200
    from app.models.notificacion import Notificacion
    notices=(await db.scalars(select(Notificacion).where(Notificacion.payload['tipo'].as_string()=='version_oferta_actualizada'))).all()
    assert notices and len({(n.evento_clave,n.destinatario_normalizado,n.canal) for n in notices})==len(notices)
    await oferta(db,admin,version='3.0.0',inc=inc,template=template)
    await db.refresh(pedido)
    assert pedido.asignacion_snapshot==frozen and pedido.seleccion_oferta_snapshot['version']=='1.0.0'


async def test_definicion_obsoleta_de_oferta_devuelve_409(client,db,admin,auth_admin,auth_catedra,catedra,perfil_capacidad):
    inc,first,template=await oferta(db,admin)
    created=await client.post('/pedidos/',json={'template_id':template.id,'modelo_servicio':'saas','vigencia':dates()},headers=auth_catedra|{'Idempotency-Key':'pedido-old'})
    _,second,template=await oferta(db,admin,version='2.0.0',inc=inc,template=template)
    result=await client.post(f"/pedidos/{created.json()['id']}/evaluacion",json={'asignacion':{'template_id':template.id,'definicion_version_id':str(first.id),'vcpus':1,'ram_mb':512,'disk_gb':4},'vigencia':dates()},headers=auth_admin)
    assert result.status_code==409,result.text
