"""Native PaaS policy, authenticated delivery and authorization regressions.

Doubles here do not certify Proxmox; the real gate is documented separately.
"""
from copy import deepcopy
from uuid import UUID
import ssl

from fastapi import HTTPException
import pymysql
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import get_settings
from app.models.servicio import Servicio
from app.models.identidad_infraestructura import IdentidadInfraestructura
from app.models.pedido import ModeloServicio
from app.schemas.configuracion_despliegue import validar_documento
from app.services import configuracion_despliegue_service as catalog
from app.services import mariadb_application_service as recipe
from app.services.application_verification_service import AccessObservation
from app.services.service_access_service import metadatos,revelar
from app.worker import procesar_una,procesar_ingesta_una
from tests.test_templates_aplicaciones_011 import app_order,catalog_image,perfil_capacidad,red_aplicaciones_011,profile_entry
from tests.test_modelos_despliegue_011 import make_configuration
from tests.test_entrega_aplicaciones_011 import DeliveredNode
from tests.test_creacion_aplicaciones_011 import stopped_create,wake
from tests.test_admision_aplicaciones_011 import approve
from infra.applications.job.configuration import validate_configuration
from infra.applications.job.protocol import JobError


@pytest.fixture
async def maria(app_order,catalog_image,monkeypatch):
    app=app_order
    _,resolver=catalog_image
    image=await resolver('mariadb:11.4',architecture='amd64')
    image.update(repositorio=recipe.REPOSITORY,tag_original='11.4',volumes=['/var/lib/mysql'])
    proof={'tipo':'proxmox_real','perfil':app.document['perfil'],'manifest_digest':image['manifest_digest'],
        'comprobaciones':['aislamiento','tls','autenticacion','persistencia','recuperacion']}
    monkeypatch.setattr(get_settings(),'mariadb_application_validation',proof)
    async def resolve(*args,**kwargs):return deepcopy(image)
    monkeypatch.setattr(catalog,'resolve_image',resolve)
    return app,proof


async def test_prepared_offer_is_paas_with_generated_private_credentials_and_no_resources(client,db,auth_admin,maria,proxmox):
    response=await client.post('/templates/aplicaciones',headers=auth_admin|{'Idempotency-Key':'maria-ready'},
        json={'nombre':'MariaDB','imagen':'mariadb:11.4','puerto':80,'modelo_servicio':'saas'})
    assert response.status_code==201,response.text
    assert response.json()['modelo_servicio']=='paas' and response.json()['oferta_disponible']
    assert not proxmox.creados
    from app.models.configuracion_despliegue import ConfiguracionDespliegue
    row=await db.get(ConfiguracionDespliegue,UUID(response.json()['configuracion_id']))
    assert row.documento['access']['tipo']=='tcp' and row.documento['access']['puerto']==3306
    assert row.documento['variables']==recipe.VARIABLES
    assert {s['nombre'] for s in row.documento['secretos']}==recipe.SECRET_NAMES
    assert all(s['modo']=='generado' and 'valor' not in s for s in row.documento['secretos'])


async def test_digest_or_validation_change_cannot_publish_maria(client,auth_admin,maria):
    _,proof=maria;proof['manifest_digest']='sha256:'+'0'*64
    response=await client.post('/templates/aplicaciones',headers=auth_admin|{'Idempotency-Key':'maria-unproven'},
        json={'nombre':'MariaDB','imagen':'mariadb:11.4','puerto':3306})
    assert response.status_code==409 and response.json()['detail']['codigo']=='mariadb_pendiente_validacion'


@pytest.mark.parametrize('mutation',['image','secret','volume','user','port'])
async def test_backend_and_node_reject_expanded_native_policy(maria,mutation):
    from app.schemas.aplicacion import AgregarAplicacion
    document=(await catalog.candidate(AgregarAplicacion(nombre='MariaDB',imagen='mariadb:11.4',puerto=3306),model='paas'))['document']
    assert validate_configuration(document)==validar_documento(document)
    if mutation=='image':document['imagen']['repositorio']='docker.io/library/mysql'
    if mutation=='secret':document['secretos'][0]['modo']='por_pedido'
    if mutation=='volume':document['persistencia']=[]
    if mutation=='user':document['variables']['MARIADB_USER']='root'
    if mutation=='port':document['access']['puerto']=3307
    with pytest.raises(HTTPException):validar_documento(document)
    with pytest.raises(JobError):validate_configuration(document)


def test_no_tls_server_is_rejected_before_any_authentication_bytes(monkeypatch):
    from app.services.mariadb_probe_service import TLSConnection
    connection=object.__new__(TLSConnection);connection.ssl=True;connection.server_capabilities=0
    monkeypatch.setattr(pymysql.connections.Connection,'_request_authentication',lambda self:pytest.fail('Credentials preceded TLS'))
    with pytest.raises(pymysql.err.OperationalError):connection._request_authentication()


async def test_delivery_requires_native_probe_and_reveals_only_catedra_password(db,engine,admin,usuario_catedra,maria,proxmox,monkeypatch,tmp_path):
    from app.schemas.aplicacion import AgregarAplicacion
    app,_=maria
    document=(await catalog.candidate(AgregarAplicacion(nombre='MariaDB',imagen='mariadb:11.4',puerto=3306),model='paas'))['document']
    config=await make_configuration(db,admin,document,revision=2)
    app.config=config;app.document=document;app.template.configuracion_despliegue_id=config.id
    app.template.modelo_servicio=ModeloServicio.PAAS;app.pedido.modelo_servicio=ModeloServicio.PAAS
    app.body['asignacion']['configuracion_despliegue_id']=str(config.id)
    await db.commit()
    sessions=async_sessionmaker(engine,expire_on_commit=False)
    await approve(db,admin,app,immediate=True);stopped_create(proxmox)
    class Node(DeliveredNode):
        async def execute(self,request,**kwargs):
            response=await super().execute(request,**kwargs)
            if request['action'] in {'read','ack'}:
                response['data']['resultado']['comprobaciones']=['runtime','salud','aislamiento','autenticacion_tcp']
            return response
    node=Node(app,sessions)
    await procesar_una(sessions,pve=proxmox,runner=node)
    db.expire_all();identity=await db.scalar(select(IdentidadInfraestructura));proxmox.estados[identity.vmid]='running'
    await wake(db)
    seen=[]
    async def probe(instance,private):
        seen.append(dict(private));assert instance['port']==3306 and set(private)=={'MARIADB_PASSWORD'}
        return AccessObservation(instance['host'],instance['address'],3306,instance['configuration_sha256'],1)
    await procesar_ingesta_una(sessions,runner=node,pve=proxmox,probe=probe)
    db.expire_all();service=await db.scalar(select(Servicio))
    assert service.disponibilidad_aplicacion=='utilizable'
    await db.refresh(usuario_catedra)
    metadata=await metadatos(db,actor=usuario_catedra,servicio_id=service.id)
    assert metadata['puede_revelar_credenciales'] and metadata['metodo']=='mariadb' and not metadata['acceso_con_nap']
    ca=tmp_path/'ca.crt';ca.write_text('-----BEGIN CERTIFICATE-----\npublic-fixture\n-----END CERTIFICATE-----\n')
    monkeypatch.setattr(get_settings(),'application_gateway_ca_file',str(ca))
    revealed=await revelar(db,actor=usuario_catedra,servicio_id=service.id)
    assert revealed['credenciales']['password']==seen[0]['MARIADB_PASSWORD']
    assert revealed['credenciales']['usuario']=='docente' and revealed['credenciales']['base']=='catedra'
    assert 'MARIADB_ROOT_PASSWORD' not in repr(revealed)
    service.estado='stopped';await db.flush()
    with pytest.raises(HTTPException):await revelar(db,actor=usuario_catedra,servicio_id=service.id)


async def test_search_suggests_prepared_version_and_native_access(client,auth_admin,maria,monkeypatch):
    from app.services import biblioteca_service
    async def search(*args,**kwargs):return {'count':1,'results':[{'repo_name':'mariadb','is_official':True}]}
    monkeypatch.setattr(biblioteca_service,'docker_hub_search',search)
    response=await client.get('/biblioteca/aplicaciones?q=mariadb',headers=auth_admin)
    item=response.json()['items'][0]
    assert item['referencia']=='mariadb:11.4' and item['compatibilidad']=='preparada'
    assert item['motivo_no_disponible'] is None


async def test_native_profile_refresh_is_one_click_and_keeps_old_snapshot(client,db,auth_admin,maria):
    from hashlib import sha256
    from app.schemas.application_profiles import canonical
    from app.models.configuracion_despliegue import ConfiguracionDespliegue
    app,proof=maria
    created=await client.post('/templates/aplicaciones',headers=auth_admin|{'Idempotency-Key':'maria-refresh-create'},
        json={'nombre':'MariaDB','imagen':'mariadb:11.4','puerto':3306})
    assert created.status_code==201,created.text
    original=await db.get(ConfiguracionDespliegue,UUID(created.json()['configuracion_id']))
    snapshot=deepcopy(original.documento)
    newer=deepcopy(app.entry);newer['definition'].update(revision=2,policy_bundle_sha256='f'*64)
    newer['sha256']=sha256(canonical(newer['definition'])).hexdigest()
    newer['validacion']['perfil_sha256']=newer['sha256']
    get_settings().application_profiles['docker-ubuntu24:2']=newer
    proof['perfil']={'id':'docker-ubuntu24','revision':2,'sha256':newer['sha256']}
    listing=(await client.get('/templates/',headers=auth_admin)).json()
    item=next(row for row in listing if row['id']==created.json()['id'])
    assert item['oferta_disponible'] is False and item['requiere_actualizar_perfil'] is True
    assert item['configuracion_actualizacion']['ruta_salud']=='/'
    refreshed=await client.post(f"/templates/{item['id']}/configuracion",headers=auth_admin|{'Idempotency-Key':'maria-refresh'},
        json=item['configuracion_actualizacion'])
    assert refreshed.status_code==200,refreshed.text
    assert refreshed.json()['oferta_disponible'] is True
    await db.refresh(original);assert original.documento==snapshot
