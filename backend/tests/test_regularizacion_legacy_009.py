from datetime import timedelta

import pytest
from sqlalchemy import select,func

from app.models.bitacora_cierre import BitacoraCierre
from app.models.compromiso_capacidad import CompromisoCapacidad
from app.models.servicio import EstadoServicio
from app.models.vigencia import VigenciaAutorizada
from app.utils.clock import clock
from tests import factories
from tests.capacity_helpers import perfil_capacidad,materializado  # noqa:F401


async def prepared(db,proxmox,catedra,usuario,template):
    service,ledger=await materializado(db,proxmox,catedra,usuario,template)
    service.asignacion_snapshot=None;service.nombre_snapshot=None
    ledger.estado='incierto'
    period=await db.scalar(select(VigenciaAutorizada))
    await db.delete(period);await db.commit()
    return service,ledger


def decision(preview):
    today=clock.now().date()
    return {'fuente_sha256':preview['fuente_sha256'],'referencia':'ACTA-LEGADO-009',
        'motivo':'Regularización de la copia comprobada','nombre':'Laboratorio histórico',
        'modelo_servicio':'iaas','asignacion':{'vcpus':2,'ram_mb':1024,'disk_gb':10},
        'desde':(today-timedelta(days=1)).isoformat(),'hasta':(today+timedelta(days=20)).isoformat()}


async def test_teacher_cannot_regularize_even_own_service(client,db,proxmox,perfil_capacidad,catedra,usuario_catedra,template,auth_catedra):
    service,_=await prepared(db,proxmox,catedra,usuario_catedra,template)
    result=await client.post(f'/servicios/{service.id}/regularizacion/evaluar',json={},headers=auth_catedra)
    assert result.status_code==403
    result=await client.post(f'/servicios/{service.id}/regularizacion',json=decision({'fuente_sha256':'a'*64}),
        headers=auth_catedra|{'Idempotency-Key':'denied-legacy'})
    assert result.status_code==403


async def test_admin_confirms_observed_allocation_and_explicit_dates_once_without_delivery(
    client,db,proxmox,perfil_capacidad,catedra,usuario_catedra,template,auth_admin,
):
    service,ledger=await prepared(db,proxmox,catedra,usuario_catedra,template)
    result=await client.post(f'/servicios/{service.id}/regularizacion/evaluar',json={},headers=auth_admin)
    assert result.status_code==200,result.text
    preview=result.json();assert preview['puede_regularizar'] and preview['desde'] is None
    payload=decision(preview);key=auth_admin|{'Idempotency-Key':'confirm-legacy'}
    result=await client.post(f'/servicios/{service.id}/regularizacion',json=payload,headers=key)
    assert result.status_code==200,result.text
    replay=await client.post(f'/servicios/{service.id}/regularizacion',json=payload,headers=key)
    assert replay.json()==result.json() and replay.headers['idempotency-replayed']=='true'
    await db.refresh(service);await db.refresh(ledger)
    assert service.disponibilidad_aplicacion=='no_verificada' and service.asignacion_snapshot['vcpus']==2
    assert service.definicion_version_id is None and service.estado==EstadoServicio.PAUSED
    assert ledger.estado=='materializado' and ledger.vcpus_retenidos==0 and ledger.disk_bytes_retenidos==10*1024**3
    assert await db.scalar(select(func.count()).select_from(BitacoraCierre))==1
    period=await db.scalar(select(VigenciaAutorizada))
    assert period.desde_local.isoformat()==payload['desde'] and period.hasta_local.isoformat()==payload['hasta']
    assert proxmox.creados==[] and proxmox.iniciados==[]


async def test_unowned_or_changed_resource_cannot_be_regularized_by_vmid(
    client,db,proxmox,perfil_capacidad,catedra,usuario_catedra,template,auth_admin,
):
    service,_=await prepared(db,proxmox,catedra,usuario_catedra,template)
    preview=(await client.post(f'/servicios/{service.id}/regularizacion/evaluar',json={},headers=auth_admin)).json()
    proxmox.configuraciones[('pve1',100)]['description']='nombre parecido no prueba propiedad'
    result=await client.post(f'/servicios/{service.id}/regularizacion',json=decision(preview),
        headers=auth_admin|{'Idempotency-Key':'changed-marker'})
    assert result.status_code==409
    await db.refresh(service);assert service.asignacion_snapshot is None
    assert await db.scalar(select(func.count()).select_from(VigenciaAutorizada))==0


async def test_quantities_must_match_observed_resource_and_no_free_override_is_accepted(
    client,db,proxmox,perfil_capacidad,catedra,usuario_catedra,template,auth_admin,
):
    service,_=await prepared(db,proxmox,catedra,usuario_catedra,template)
    preview=(await client.post(f'/servicios/{service.id}/regularizacion/evaluar',json={},headers=auth_admin)).json()
    service_id=service.id
    payload=decision(preview);payload['asignacion']['vcpus']=3
    result=await client.post(f'/servicios/{service_id}/regularizacion',json=payload,
        headers=auth_admin|{'Idempotency-Key':'wrong-allocation'})
    assert result.status_code==409
    payload=decision(preview)|{'disponibilidad_aplicacion':'utilizable'}
    assert (await client.post(f'/servicios/{service_id}/regularizacion',json=payload,
        headers=auth_admin|{'Idempotency-Key':'forbidden-override'})).status_code==422


async def test_uncertain_ledger_blocks_direct_restart_without_regularization(
    client,db,proxmox,perfil_capacidad,catedra,usuario_catedra,template,auth_admin,
):
    service,ledger=await materializado(db,proxmox,catedra,usuario_catedra,template)
    service.estado=EstadoServicio.RUNNING;ledger.estado='incierto';await db.commit()
    result=await client.post(f'/servicios/{service.id}/restart',json={},headers=auth_admin|{'Idempotency-Key':'deny-uncertain-restart'})
    assert result.status_code==409 and result.json()['detail']['codigo']=='reconciliacion_pendiente'


async def test_duplicate_is_archived_only_against_proven_canonical_same_category_without_guest_delete(
    client,db,proxmox,perfil_capacidad,catedra,usuario_catedra,template,auth_admin,
):
    canonical,_=await materializado(db,proxmox,catedra,usuario_catedra,template)
    duplicate=await factories.crear_servicio(db,catedra.id,template.id,proxmox_vmid='0100')
    preview=await client.post(f'/servicios/{duplicate.id}/regularizacion/evaluar',json={'canonico_id':canonical.id},headers=auth_admin)
    assert preview.status_code==200 and preview.json()['puede_archivar_duplicado']
    result=await client.post(f'/servicios/{duplicate.id}/regularizacion/archivar-duplicado',headers=auth_admin|{'Idempotency-Key':'archive-duplicate'},
        json={'fuente_sha256':preview.json()['fuente_sha256'],'canonico_id':canonical.id,
            'referencia':'ACTA-DUPLICADO','motivo':'Registro duplicado contrastado'})
    assert result.status_code==200,result.text
    await db.refresh(duplicate);await db.refresh(canonical)
    assert duplicate.deleted_at is not None and canonical.deleted_at is None
    assert proxmox.eliminados==[] and len(proxmox.recursos)==1


async def test_running_outside_explicit_period_queues_pause_and_keeps_capacity_until_effect(
    client,db,proxmox,perfil_capacidad,catedra,usuario_catedra,template,auth_admin,
):
    from app.models.operacion_infraestructura import OperacionInfraestructura
    service,ledger=await prepared(db,proxmox,catedra,usuario_catedra,template)
    service.estado=EstadoServicio.RUNNING;proxmox.recursos[0]['status']='running';await db.commit()
    preview=(await client.post(f'/servicios/{service.id}/regularizacion/evaluar',json={},headers=auth_admin)).json()
    payload=decision(preview);payload['desde']=(clock.now().date()+timedelta(days=7)).isoformat()
    result=await client.post(f'/servicios/{service.id}/regularizacion',json=payload,
        headers=auth_admin|{'Idempotency-Key':'future-period-pause'})
    assert result.status_code==200,result.text
    assert result.json()['operation_id']
    operation=await db.scalar(select(OperacionInfraestructura))
    await db.refresh(service);await db.refresh(ledger)
    assert operation.tipo=='pausar' and operation.estado=='pendiente' and operation.actor_tipo=='sistema'
    assert service.estado==EstadoServicio.RUNNING and ledger.vcpus_retenidos==2 and ledger.ram_mb_retenida==1024
    assert ledger.disk_bytes_retenidos==10*1024**3 and proxmox.detenidos==[]


async def test_existing_authorized_period_cannot_be_replaced_by_regularization(
    client,db,proxmox,perfil_capacidad,catedra,usuario_catedra,template,auth_admin,
):
    service,ledger=await materializado(db,proxmox,catedra,usuario_catedra,template)
    ledger.estado='incierto';await db.commit();service_id=service.id
    original=await db.scalar(select(VigenciaAutorizada));original_id=original.id
    preview=(await client.post(f'/servicios/{service_id}/regularizacion/evaluar',json={},headers=auth_admin)).json()
    payload=decision(preview);payload['hasta']=(original.hasta_local+timedelta(days=1)).isoformat()
    result=await client.post(f'/servicios/{service_id}/regularizacion',json=payload,
        headers=auth_admin|{'Idempotency-Key':'no-replace-period'})
    assert result.status_code==409 and result.json()['detail']['codigo']=='vigencia_ya_autorizada'
    assert await db.scalar(select(func.count()).select_from(BitacoraCierre))==0
    assert (await db.scalar(select(VigenciaAutorizada))).id==original_id


@pytest.mark.parametrize('case',['no-marker','other-category','published'])
async def test_duplicate_without_proof_or_outside_legacy_scope_stays_pending(
    case,client,db,proxmox,perfil_capacidad,catedra,usuario_catedra,template,auth_admin,
):
    canonical,_=await materializado(db,proxmox,catedra,usuario_catedra,template)
    duplicate=await factories.crear_servicio(db,catedra.id,template.id,proxmox_vmid='0100')
    if case=='no-marker': proxmox.configuraciones[('pve1',100)]['description']='sin prueba de propiedad'
    if case=='other-category':
        other=await factories.crear_catedra(db,nombre='Otra cátedra de revisión')
        duplicate.catedra_id=other.id
    if case=='published':
        duplicate.definicion_version_id=template.definicion_version_id
    await db.commit();duplicate_id=duplicate.id
    preview=(await client.post(f'/servicios/{duplicate_id}/regularizacion/evaluar',json={'canonico_id':canonical.id},headers=auth_admin)).json()
    assert not preview['puede_archivar_duplicado']
    result=await client.post(f'/servicios/{duplicate_id}/regularizacion/archivar-duplicado',
        headers=auth_admin|{'Idempotency-Key':'no-archive-'+case},json={'fuente_sha256':preview['fuente_sha256'],
            'canonico_id':canonical.id,'referencia':'ACTA-RECHAZADA','motivo':'Revisión sin prueba suficiente'})
    assert result.status_code==409
    assert (await db.get(type(duplicate),duplicate_id)).deleted_at is None
    assert proxmox.eliminados==[]
