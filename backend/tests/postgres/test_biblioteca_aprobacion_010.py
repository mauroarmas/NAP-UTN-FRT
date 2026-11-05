import asyncio
from datetime import timedelta
from copy import deepcopy
from unittest.mock import AsyncMock
from uuid import UUID
from sqlalchemy import select,func
from fastapi import HTTPException
from app.models.usuario import Usuario
from app.models.pedido import Pedido
from app.models.recurso_template import RecursoTemplate
from app.models.ensayo_preparacion import EnsayoPreparacion
from app.models.artefacto_preparado import ArtefactoPreparado,ReplicaArtefacto
from app.models.presupuesto_builder import PresupuestoBuilder
from app.models.compromiso_capacidad import CompromisoCapacidad
from app.schemas.ensayo import PublicarOferta
from app.services import admision_service,catalogo_service
from app.utils.clock import clock
from tests.test_biblioteca_pedidos_010 import oferta
from tests.test_perfiles_definiciones_009 import dates
from tests.capacity_helpers import perfil_capacidad


async def test_publicar_y_aprobar_serializan_snapshot(client,db,pg_sessions,admin,catedra,auth_admin,auth_catedra,perfil_capacidad,proxmox,monkeypatch):
    inc,first,template=await oferta(db,admin)
    perfil_capacidad['cluster_id']=first.manifest['validation']['cluster_uuid']
    proxmox.contenidos_storage[('pve1','local')]=[{'volid':first.manifest['image']['volume_id'],'content':'vztmpl'}]
    created=await client.post('/pedidos/',json={'template_id':template.id,'modelo_servicio':'saas','vigencia':dates()},headers=auth_catedra|{'Idempotency-Key':'race-request'})
    pid=created.json()['id'];aid=admin.id
    selection={'asignacion':{'template_id':template.id,'definicion_version_id':str(first.id),'vcpus':1,'ram_mb':512,'disk_gb':4},'vigencia':dates()}
    evaluation=await client.post(f'/pedidos/{pid}/evaluacion',json=selection,headers=auth_admin)
    assert evaluation.status_code==200,evaluation.text
    approval=selection|{'capacidad_token':evaluation.json()['capacidad_token']}
    _,second,template=await oferta(db,admin,version='2.0.0',inc=inc,template=template,estado='validada')
    template.definicion_version_id=first.id;template.revision-=1
    db.add(PresupuestoBuilder(scope_id='race-builder',revision_config=1,limite_bytes=1000))
    trial=EnsayoPreparacion(incorporacion_id=inc.id,definicion_id=second.id,perfil_id='prueba',creado_por=aid,
        estado='comprobada',expires_at=clock.now()+timedelta(hours=24),aviso_at=clock.now(),evidencia_id=second.evidencia_validacion)
    db.add(trial);await db.flush()
    artifact=ArtefactoPreparado(definicion_id=second.id,entradas_sha256='b'*64,registro_id='prueba',scope_id='race-builder',estado='disponible',
        volume_id=second.manifest['image']['volume_id'],image_sha256=second.manifest['image']['sha256'],image_bytes=1,
        bundle_sha256=second.manifest['preparation']['bundle_sha256'],bundle_bytes=1,manifest=deepcopy(second.manifest),saneamiento={})
    db.add(artifact);await db.flush();trial.artefacto_id=artifact.id
    db.add(ReplicaArtefacto(artefacto_id=artifact.id,nodo='pve1',storage_id='local',image_sha256=artifact.image_sha256,
        bundle_sha256=artifact.bundle_sha256,registro_revision=second.manifest_sha256))
    publish=PublicarOferta(revision_esperada=second.revision,ensayo_id=trial.id,perfil={'template_id':template.id,
        'revision_esperada':template.revision,'nombre':template.nombre,'descripcion':'Draw.io comprobado','default_vcpus':1,'default_ram_mb':512,'default_disk_gb':4})
    did=second.id;await db.commit()
    monkeypatch.setattr(catalogo_service,'comprobar_disponibilidad',AsyncMock())
    barrier=asyncio.Barrier(2)
    async def run(kind):
        async with pg_sessions() as session:
            actor=await session.get(Usuario,aid);await barrier.wait()
            try:
                result=await (catalogo_service.publicar_oferta(session,did,actor=actor,data=publish,clave='race-publish') if kind=='publish'
                    else admision_service.aprobar(session,pid,actor=actor,payload=approval,clave='race-approve',pve=proxmox))
                await session.commit();return result.status_code
            except HTTPException as exc:await session.rollback();return exc.status_code
    pub,approved=await asyncio.gather(run('publish'),run('approve'))
    assert pub==200 and approved in {200,409}
    pedido=await db.get(Pedido,pid,populate_existing=True)
    count=await db.scalar(select(func.count()).select_from(CompromisoCapacidad).where(CompromisoCapacidad.pedido_id==pid))
    if approved==200:assert pedido.asignacion_snapshot['definition_version']=='1.0.0' and count==1
    else:assert pedido.estado.value=='solicitado' and count==0
