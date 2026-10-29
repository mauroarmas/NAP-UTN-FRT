"""Disponibilidad del perfil y su definición; sin parámetros PVE del docente."""
from sqlalchemy import select

from app.models.definicion_servicio import DefinicionServicio
from app.models.recurso_template import TipoRecurso
from app.schemas.definicion import digest
from app.services.catalogo_service import comprobar_evidencia
from app.utils.errors import error
from app.schemas.tamanos import tamanos_compatibles, identificar_tamano


async def exigir_configuracion(db, template, *, bloquear=False):
    """New offers use an immutable declaration, never a legacy definition adapter."""
    from app.models.configuracion_despliegue import ConfiguracionDespliegue
    from app.schemas.configuracion_despliegue import validar_documento, digest_configuracion
    from app.services.application_profiles_service import require_profile
    query=select(ConfiguracionDespliegue).where(ConfiguracionDespliegue.id==template.configuracion_despliegue_id)
    if bloquear:query=query.with_for_update()
    row=await db.scalar(query.execution_options(populate_existing=True))
    if (not row or row.estado!='validada' or not template.activo or template.tipo!=TipoRecurso.LXC
            or template.definicion_version_id or row.modelo_servicio!=template.modelo_servicio.value):
        raise error(409,'configuracion_no_disponible','La aplicación seleccionada ya no está disponible')
    document=validar_documento(row.documento)
    from app.services.application_compatibility_service import require_document
    require_document(document)
    if (row.sha256!=digest_configuracion(document) or row.origen!=document['origen']
            or row.modelo_servicio!=document['modelo_servicio']
            or document['perfil']!={'id':row.perfil_id,'revision':row.perfil_revision,'sha256':row.perfil_sha256}
            or template.os_template not in (None,document['base']['volumen_lxc'])):
        raise error(409,'configuracion_no_disponible','La configuración de la aplicación requiere revisión')
    profile=require_profile(document['perfil'])
    if (profile['base']!=document['base'] or profile['origen']!=document['origen']
            or any(document['minimum_resources'][key]<value for key,value in profile['minimum_resources'].items())
            or not tamanos_compatibles(document['minimum_resources'])):
        raise error(409,'perfil_aplicacion_no_disponible','La aplicación no es compatible con los tamaños disponibles')
    return row,document,profile


async def validar_asignacion_aplicacion(db,pedido):
    """Use the approved revision after catalog changes, with current safety gates."""
    from app.config import get_settings
    from app.models.configuracion_despliegue import ConfiguracionDespliegue
    from app.schemas.configuracion_despliegue import validar_documento,digest_configuracion
    from app.services.application_profiles_service import require_profile
    from app.services.reserva_red_service import validar_red_aplicacion
    snapshot=pedido.asignacion_snapshot or {};destination=pedido.destino_snapshot or {}
    row=await db.get(ConfiguracionDespliegue,pedido.configuracion_despliegue_id)
    try:
        document=validar_documento(snapshot['configuracion'])
        from app.services.application_compatibility_service import require_document
        require_document(document)
        if (not row or row.estado not in {'validada','retirada'} or snapshot['configuracion_despliegue_id']!=str(row.id)
                or snapshot['configuracion_sha256']!=row.sha256 or digest_configuracion(document)!=row.sha256
                or snapshot['configuracion_revision']!=row.revision
                or document!=row.documento or snapshot['origen']!=document['origen']
                or snapshot['image']!={'volume_id':document['base']['volumen_lxc'],'sha256':document['base']['sha256']}):
            raise ValueError()
        if (identificar_tamano(snapshot) is None or snapshot['minimum_resources']!=document['minimum_resources']
                or any(snapshot[key]<value for key,value in document['minimum_resources'].items())):raise ValueError()
        profile=require_profile(document['perfil'],cluster_uuid=get_settings().infrastructure_profile['cluster_id'],node=destination['nodo'])
        network,digest=validar_red_aplicacion(profile['network_profile_id'],cluster_uuid=profile['cluster_uuid'],node=destination['nodo'])
        if (snapshot['perfil_snapshot']!=profile or snapshot['perfil']!=document['perfil']
                or snapshot['network_sha256']!=digest or snapshot['network_revision']!=network['revision']
                or snapshot['network_profile_id']!=profile['network_profile_id'] or snapshot['network_snapshot']!=network):raise ValueError()
    except (KeyError,ValueError,TypeError):
        raise error(409,'asignacion_aplicacion_cambiada','La configuración aprobada requiere revisión antes de desplegar') from None
    return row,document,profile


def compatible(template, definition):
    if (not definition or template.tipo != TipoRecurso.LXC or not template.activo
        or definition.estado != 'publicada' or definition.modelo_servicio != template.modelo_servicio.value
        or not definition.manifest_sha256 or definition.manifest_sha256 != digest(definition.manifest)
        or not definition.evidencia_validacion):
        return False
    minimum = definition.manifest.get('minimum_resources', {})
    image = definition.manifest.get('image', {}).get('volume_id')
    return bool(image and tamanos_compatibles(minimum) and template.os_template in (None, image) and all(
        key in minimum and getattr(template, field) >= minimum[key]
        for field, key in [('default_vcpus', 'vcpus'), ('default_ram_mb', 'ram_mb'), ('default_disk_gb', 'disk_gb')]))


async def exigir_definicion(db, template, *, bloquear=False):
    if template.configuracion_despliegue_id:
        await exigir_configuracion(db,template,bloquear=bloquear)
        return None
    from app.services.bases_iaas_service import es_base, disponible
    if es_base(template):
        if not disponible(template):
            raise error(422, 'base_iaas_no_disponible', 'La base Linux o su red no están disponibles.')
        return None
    if not template.definicion_version_id:
        raise error(422, 'definicion_requerida', 'El perfil necesita una definición publicada compatible')
    query = select(DefinicionServicio).where(DefinicionServicio.id == template.definicion_version_id)
    if bloquear:
        query = query.with_for_update()
    definition = await db.scalar(query.execution_options(populate_existing=True))
    if not compatible(template, definition):
        raise error(422, 'oferta_no_disponible', 'Revisá definición publicada, modelo, mínimos e imagen del perfil')
    proof = await comprobar_evidencia(db, definition)
    if proof.id != definition.evidencia_validacion:
        raise error(409, 'evidencia_desactualizada', 'La referencia validada de la definición cambió')
    return definition


async def anexar_disponibilidad(db, templates):
    ids = {row.definicion_version_id for row in templates if row.definicion_version_id}
    definitions = {row.id: row for row in (await db.scalars(select(DefinicionServicio).where(DefinicionServicio.id.in_(ids)))).all()} if ids else {}
    for row in templates:
        if row.configuracion_despliegue_id:
            from fastapi import HTTPException
            row.oferta_disponible=False
            row.requiere_actualizar_perfil=False
            row.configuracion_actualizacion=None
            row.motivo_no_disponible=None
            row.minimum_resources=None;row.tamanos_permitidos=[];row.tamano_recomendado=None
            row.origen_biblioteca=False;row.version_ofrecida=None;row.codigo_definicion=None
            try:
                _,document,_=await exigir_configuracion(db,row)
                row.minimum_resources=document['minimum_resources']
                row.tamanos_permitidos=tamanos_compatibles(row.minimum_resources)
                row.tamano_recomendado=next(iter(row.tamanos_permitidos),None)
                row.oferta_disponible=True;row.origen_biblioteca=document['origen']=='community_scripts'
            except HTTPException as exc:
                row.motivo_no_disponible=exc.detail.get('mensaje') if isinstance(exc.detail,dict) else str(exc.detail)
                from app.models.configuracion_despliegue import ConfiguracionDespliegue
                from app.schemas.configuracion_despliegue import validar_documento
                from app.services.configuracion_despliegue_service import choose_profile
                cfg=await db.get(ConfiguracionDespliegue,row.configuracion_despliegue_id)
                if cfg and cfg.estado=='validada':
                    try:
                        doc=validar_documento(cfg.documento)
                        from app.services.application_compatibility_service import require_document
                        active_ref,_=choose_profile()
                        # Check whether the current prepared recipe can replace
                        # this historical profile; never mutate its snapshot.
                        require_document({**doc,'perfil':active_ref})
                        row.minimum_resources=doc['minimum_resources']
                        row.tamanos_permitidos=tamanos_compatibles(row.minimum_resources)
                        row.tamano_recomendado=next(iter(row.tamanos_permitidos),None)
                        if doc['perfil']!=active_ref:
                            img=doc['imagen']
                            imagen_ref=f"{img['repositorio']}:{img['tag_original']}" if img.get('tag_original') else f"{img['repositorio']}@{img['manifest_digest']}"
                            row.requiere_actualizar_perfil=True
                            row.configuracion_actualizacion={
                                'origen':doc['origen'],
                                'imagen':imagen_ref,
                                'puerto':doc['access']['puerto'],
                                'modelo_servicio':doc['modelo_servicio'],
                                'variables':doc.get('variables',{}),
                                'secretos':doc.get('secretos',[]),
                                'persistencia':doc.get('persistencia',[]),
                                'ruta_salud':doc['access']['probe'].get('path','/'),
                                'websocket':doc['access'].get('websocket',False),
                                'revision_esperada':row.revision,
                            }
                    except Exception:
                        pass
            continue
        from app.services.bases_iaas_service import es_base, disponible
        if es_base(row):
            from app.schemas.tamanos import TAMANOS
            row.minimum_resources = dict(TAMANOS['small'])
            row.tamanos_permitidos = list(TAMANOS)
            row.tamano_recomendado = identificar_tamano({key: getattr(row, 'default_' + key) for key in TAMANOS['small']}) or 'small'
            row.oferta_disponible = disponible(row)
            row.origen_biblioteca = False
            continue
        definition = definitions.get(row.definicion_version_id)
        minimum = (definition.manifest or {}).get('minimum_resources') if definition else None
        row.codigo_definicion = definition.codigo if definition else None
        row.minimum_resources = minimum
        row.tamanos_permitidos = tamanos_compatibles(minimum)
        preferred = identificar_tamano({key: getattr(row, 'default_' + key) for key in ['vcpus', 'ram_mb', 'disk_gb']})
        row.tamano_recomendado = preferred if preferred in row.tamanos_permitidos else next(iter(row.tamanos_permitidos), None)
        row.oferta_disponible = compatible(row, definition)
        row.origen_biblioteca = bool(definition and definition.incorporacion_id)
        row.version_ofrecida = definition.version if row.origen_biblioteca else None
    return templates
