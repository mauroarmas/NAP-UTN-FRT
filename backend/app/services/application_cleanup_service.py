"""Release only the retired instance's host rules before returning its VMID."""
from app.services.application_job_client import ApplicationJobClient
from app.services.infraestructura_io import InfraNoVerificable
from app.utils.secretos import configured_keyring
from infra.applications.job.protocol import PROTOCOL,canonical,parse_response,JobError


async def release(identity,*,runner=None):
    nonce=configured_keyring().decrypt(identity.nonce_cifrado,context=f'infra:{identity.resource_uuid}:nonce')
    request={'protocol':PROTOCOL,'action':'cleanup','cluster_uuid':identity.cluster_id,
        'node':identity.nodo,'vmid':identity.vmid,'resource_uuid':str(identity.resource_uuid),'nonce':nonce}
    try:
        response=await (runner or ApplicationJobClient()).execute(request)
        response=parse_response(canonical(response),request=request)
        if not response['ok']:raise JobError('UNCONFIRMED')
    except (JobError,TimeoutError,OSError):raise InfraNoVerificable(incierto=True) from None
