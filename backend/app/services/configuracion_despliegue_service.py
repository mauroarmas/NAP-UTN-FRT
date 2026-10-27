"""Validate metadata without a transaction, then atomically add a reusable offer."""
from copy import deepcopy
from hashlib import sha256
import json
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.models.configuracion_despliegue import ConfiguracionDespliegue
from app.models.decision_idempotente import DecisionIdempotente
from app.models.recurso_template import RecursoTemplate,TipoRecurso
from app.models.pedido import ModeloServicio
from app.models.usuario import Usuario
from app.schemas.aplicacion import AgregarAplicacion,RevisarAplicacion
from app.schemas.configuracion_despliegue import validar_documento,digest_configuracion
from app.schemas.oci_registry import RegistryProfile
from app.schemas.tamanos import TAMANOS,tamanos_compatibles
from app.services import application_profiles_service as profiles
from app.services.acceso_service import requiere_admin_actual
from app.services.idempotencia_service import ejecutar,ResultadoDecision
from app.services.perfiles_service import anexar_disponibilidad
from app.services.oci_registry_service import resolve_image
from app.utils.clock import clock
from app.utils.errors import error


def conflict():return error(409,'oferta_cambiada','La oferta o su configuración cambió. Volvé a revisarla.')


def choose_profile():
    settings=get_settings();choices=[]
    for entry in profiles.profile_capabilities():
        if entry['estado']!='habilitado':continue
        ref={k:entry[k] for k in ('id','revision','sha256')}
        definition=profiles.require_profile(ref)
        if definition['origen']=='imagen_docker' and definition['cluster_uuid']==settings.infrastructure_profile.get('cluster_id'):choices.append((ref,definition))
    if not choices:raise error(409,'perfil_aplicacion_no_disponible','La infraestructura todavía no admite aplicaciones desde imágenes.')
    return sorted(choices,key=lambda p:(p[0]['id'],-p[0]['revision']))[0]


def registry_hash(profile):
    return sha256(json.dumps(RegistryProfile.model_validate(profile).model_dump(),sort_keys=True,separators=(',',':')).encode()).hexdigest()


async def candidate(body,*,model,resolver=None):
    reference,profile=choose_profile()
    image=await (resolver or resolve_image)(body.imagen,architecture=profile['base']['arquitectura'])
    if not set(image['volumes'])<=set(body.persistencia):
        raise error(422,'persistencia_requerida','La imagen necesita carpetas persistentes. Completalas en las opciones de la aplicación.')
    document=validar_documento({'schema_version':'nap-deployment/1','origen':'imagen_docker',
        'modelo_servicio':model,'perfil':reference,'base':profile['base'],'minimum_resources':profile['minimum_resources'],
        'access':{'tipo':'web','puerto':body.puerto,'politica':'web-managed','upstream':'http',
            'probe':{'tipo':'http','path':body.ruta_salud,'estados':[200],'timeout_segundos':10},'websocket':body.websocket},
        'variables':body.variables,'secretos':[s.model_dump(mode='json') for s in body.secretos],
        'persistencia':body.persistencia,'imagen':{key:image[key] for key in ('repositorio','tag_original','manifest_digest',
            'index_digest','config_digest','os','arquitectura','registry_profile_id')}})
    return {'document':document,'profile':profile,'registry_sha256':image['registry_profile_sha256']}


async def change(db,*,actor,body,clave,template_id=None,resolver=None):
    if type(clave) is not str or not 1<=len(clave)<=128 or not clave.strip():
        raise error(422,'idempotency_key_invalida','Indicá una clave idempotente de hasta 128 caracteres')
    actor=await requiere_admin_actual(db,actor);actor_id=actor.id
    create=template_id is None
    body=body if isinstance(body,AgregarAplicacion if create else RevisarAplicacion) else (AgregarAplicacion if create else RevisarAplicacion).model_validate(body)
    path='/templates/aplicaciones' if create else f'/templates/{template_id}/configuracion'
    payload=body.model_dump(mode='json')
    async def impossible(session):raise RuntimeError('Unreachable replay decision')
    prior=await db.scalar(select(DecisionIdempotente.id).where(DecisionIdempotente.actor_tipo=='usuario',
        DecisionIdempotente.actor_id_normalizado==str(actor_id),DecisionIdempotente.idempotency_key==clave))
    if prior is not None:
        return await ejecutar(db,actor_id=actor_id,clave=clave,metodo='POST',ruta=path,payload=payload,decidir=impossible)
    template=await db.get(RecursoTemplate,template_id) if not create else None
    if not create and (template is None or template.revision!=body.revision_esperada):raise conflict()
    model=body.modelo_servicio or (template.modelo_servicio.value if template else 'saas')
    # The authorization/catalog reads are complete before contacting a registry.
    await db.commit()
    prepared=await candidate(body,model=model,resolver=resolver)
    async def decide(session):
        current_actor=await session.get(Usuario,actor_id,populate_existing=True)
        if current_actor is None:raise error(403,'sin_permisos','La cuenta ya no tiene acceso operativo')
        await requiere_admin_actual(session,current_actor)
        document=prepared['document']
        profile=profiles.require_profile(document['perfil'],cluster_uuid=get_settings().infrastructure_profile.get('cluster_id'))
        registry=get_settings().application_registry_profiles.get(document['imagen']['registry_profile_id'])
        if profile!=prepared['profile'] or not registry or registry_hash(registry)!=prepared['registry_sha256']:raise conflict()
        if create:
            if await session.scalar(select(RecursoTemplate.id).where(RecursoTemplate.nombre==body.nombre)):raise conflict()
            item=RecursoTemplate(nombre=body.nombre,descripcion=body.descripcion,tipo=TipoRecurso.LXC,
                modelo_servicio=ModeloServicio(model),activo=True,revision=1)
            session.add(item);codigo='app-'+uuid4().hex;revision=1
        else:
            item=await session.scalar(select(RecursoTemplate).where(RecursoTemplate.id==template_id).with_for_update().execution_options(populate_existing=True))
            if item is None or item.revision!=body.revision_esperada:raise conflict()
            previous=await session.get(ConfiguracionDespliegue,item.configuracion_despliegue_id) if item.configuracion_despliegue_id else None
            codigo=previous.codigo if previous else 'app-'+uuid4().hex
            revision=previous.revision+1 if previous else 1
            item.revision+=1;item.modelo_servicio=ModeloServicio(model)
        row=ConfiguracionDespliegue(codigo=codigo,revision=revision,origen=document['origen'],modelo_servicio=model,
            documento=deepcopy(document),sha256=digest_configuracion(document),perfil_id=document['perfil']['id'],
            perfil_revision=document['perfil']['revision'],perfil_sha256=document['perfil']['sha256'],creado_por=actor_id,
            validaciones={'tipo':'metadatos_oci','registry_profile_sha256':prepared['registry_sha256'],
                'observado_at':clock.now().isoformat(),'ejecucion_realizada':False})
        session.add(row);await session.flush()
        item.configuracion_despliegue_id=row.id;item.definicion_version_id=None;item.os_template=document['base']['volumen_lxc']
        size=tamanos_compatibles(document['minimum_resources'])[0]
        for key,value in TAMANOS[size].items():setattr(item,'default_'+key,value)
        await session.flush();await anexar_disponibilidad(session,[item])
        from app.schemas.template import TemplateResponse
        response=TemplateResponse.model_validate(item).model_dump(mode='json')
        response.update(origen_despliegue=document['origen'],configuracion_id=str(row.id),estado_presentacion='Disponible para solicitar')
        return ResultadoDecision(201 if create else 200,response)
    try:
        return await ejecutar(db,actor_id=actor_id,clave=clave,metodo='POST',ruta=path,payload=payload,decidir=decide)
    except IntegrityError:
        await db.rollback();raise conflict() from None
