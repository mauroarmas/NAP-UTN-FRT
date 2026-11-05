from tests.fakes_biblioteca import DRAWIO
import pytest


async def test_revision_historica_nap_independiente_y_ensayo_sin_perfil(client, db, admin, auth_admin):
    from app.models.incorporacion_aplicacion import IncorporacionAplicacion
    row=IncorporacionAplicacion(**{k:DRAWIO[k] for k in ['identidad_externa','revision_fuente',
        'comando_sha256','comando_origen','url_origen','nombre','descripcion','categorias','aliases']},
        origen_clave='historica',creado_por=admin.id)
    db.add(row);await db.commit()
    inc={'id':str(row.id),'revision':row.revision};url=f"/biblioteca/incorporaciones/{inc['id']}/definicion"
    body={'revision_esperada':inc['revision'],'codigo':'drawio-curso','version':'1.0.0'}
    first=await client.post(url,json=body,headers=auth_admin|{'Idempotency-Key':'v1'})
    assert first.status_code==201,first.text
    second=await client.post(url,json=body|{'version':'2.0.0','base_definicion_id':first.json()['id']},headers=auth_admin|{'Idempotency-Key':'v2'})
    assert second.status_code==201,second.text
    assert first.json()['id']!=second.json()['id']
    repeat=await client.post(url,json=body|{'version':'2.0.0','base_definicion_id':first.json()['id']},headers=auth_admin|{'Idempotency-Key':'v2-otra'})
    assert repeat.status_code==200 and repeat.json()['id']==second.json()['id']
    start=await client.post(f"/definiciones/{first.json()['id']}/ensayos",json={'incorporacion_id':inc['id'],'revision_esperada':1,'perfil_ensayo_id':'inexistente','plazo_horas':24},headers=auth_admin|{'Idempotency-Key':'ensayo'})
    assert start.status_code==409 and start.json()['detail']['codigo']=='ensayo_no_preparado'


async def test_no_publicar_drawio_por_ruta_previa(client,auth_admin):
    result=await client.post('/definiciones',json={'codigo':'drawio-test','version':'1.0.0','producto':'drawio','modelo_servicio':'saas'},headers=auth_admin|{'Idempotency-Key':'drawio'})
    assert result.status_code==201,result.text
    result=await client.post(f"/definiciones/{result.json()['id']}/publicar",json={},headers=auth_admin|{'Idempotency-Key':'pub'})
    assert result.status_code==409


async def test_ensayo_roles_cas_eventos_y_acceso_sensible(client,db,admin,auth_admin,auth_catedra):
    from tests.test_ensayo_limpieza_010 import make_trial
    trial=await make_trial(db,admin);await db.commit()
    url=f'/ensayos/{trial.id}'
    assert (await client.get(url)).status_code==401
    assert (await client.get(url,headers=auth_catedra)).status_code==403
    detail=await client.get(url,headers=auth_admin)
    assert detail.status_code==200 and 'operaciones' in detail.json()
    unknown=await client.post(url+'/descartar',json={'revision_esperada':1,'motivo':'Cerrar','shell':'no'},headers=auth_admin|{'Idempotency-Key':'extra'})
    assert unknown.status_code==422
    wrong=await client.post(url+'/descartar',json={'revision_esperada':9,'motivo':'Cerrar'},headers=auth_admin|{'Idempotency-Key':'cas'})
    assert wrong.status_code==409
    discarded=await client.post(url+'/descartar',json={'revision_esperada':1,'motivo':'Cerrar'},headers=auth_admin|{'Idempotency-Key':'discard-api'})
    assert discarded.status_code==202 and discarded.json()['limpieza_estado']=='pendiente'
    events=await client.get(url+'/eventos?limit=1',headers=auth_admin)
    assert events.status_code==200 and len(events.json()['items'])==1
    assert 'next_cursor' in events.json()
    from uuid import uuid4
    access=await client.post(url+f'/recursos/{uuid4()}/revelar-acceso',headers=auth_admin)
    assert access.status_code==404 and access.headers.get('cache-control')=='no-store'
