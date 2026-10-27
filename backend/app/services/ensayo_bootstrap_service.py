"""Bootstrap sólo del artefacto ligado al ensayo; no relaja producción."""
import secrets
from uuid import UUID
from app.config import get_settings
from app.models.identidad_infraestructura import IdentidadInfraestructura
from app.schemas.definicion import digest
from app.services import probes_servicio
from app.utils.secretos import configured_keyring
from app.utils.errors import error


async def preparar_peticion(db,trial,resource,artifact,operation_id):
    identity=await db.get(IdentidadInfraestructura,resource.identidad_infraestructura_id)
    if not identity or identity.recurso_ensayo_id!=resource.id or identity.ausencia_confirmada_at or artifact.id!=trial.artefacto_id:
        raise error(409,'ensayo_sin_propiedad','No se acredita el recurso del ensayo')
    if digest(artifact.manifest)!=identity.definition_sha256 or artifact.bundle_sha256!=identity.bundle_sha256:
        raise error(409,'artefacto_alterado','El artefacto cambió después de crear el recurso')
    if not resource.credenciales_encrypted:
        resource.credenciales_encrypted=configured_keyring().encrypt({'access_password':secrets.token_urlsafe(32)},context=f'ensayo:{resource.id}:secretos')
    values=configured_keyring().decrypt(resource.credenciales_encrypted,context=f'ensayo:{resource.id}:secretos')
    return {'protocol':'nap-guest-runner/1','operation_id':str(operation_id),'action':'bootstrap',
        'cluster_uuid':identity.cluster_id,'resource_uuid':str(identity.resource_uuid),'node':identity.nodo,'vmid':identity.vmid,
        'pool':identity.pool_catedra,'nonce':configured_keyring().decrypt(identity.nonce_cifrado,context=f'infra:{identity.resource_uuid}:nonce'),
        'definition_key':artifact.manifest['definition_key'],'definition_version':artifact.manifest['definition_version'],
        'definition_sha256':identity.definition_sha256,'bundle_sha256':identity.bundle_sha256,
        'network_profile_id':resource.destino_snapshot['network_profile_id'],'parameters':{'display_name':'Ensayo Draw.io'},'secrets':values}


def confirmar(resource,request,response,operation_id):
    profile=get_settings().network_profiles[request['network_profile_id']]
    return probes_servicio.confirmar(response,request,product='drawio',profile=profile,service_id=0,preparation_id=operation_id)
