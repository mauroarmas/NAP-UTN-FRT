"""Resolve an application destination exclusively from its approved identity.

No browser URL, stale catalog revision, legacy password, or DNS lookup supplies
an upstream. Callers authorize the actor before invoking this internal helper.
"""
from hashlib import sha256
from sqlalchemy import select

from app.config import get_settings
from app.models.identidad_infraestructura import IdentidadInfraestructura
from app.models.pedido import Pedido
from app.models.reserva_red_aplicacion import ReservaRedAplicacion
from app.services.perfiles_service import validar_asignacion_aplicacion
from app.utils.errors import error
from app.utils.secretos import configured_keyring, SecretError


def unavailable():
    return error(409,'destino_no_confirmado','No se pudo confirmar la dirección de esta aplicación.')


async def destination(db, service, *, prepared=True):
    identity=await db.get(IdentidadInfraestructura,service.identidad_infraestructura_id,populate_existing=True) if service.identidad_infraestructura_id else None
    order=await db.get(Pedido,service.pedido_id,populate_existing=True) if service.pedido_id else None
    if (not identity or not order or service.deleted_at is not None
            or identity.servicio_id!=service.id or identity.estado!='materializada'
            or identity.ausencia_confirmada_at or not identity.ownership_verificada_at
            or order.catedra_id!=service.catedra_id
            or service.configuracion_despliegue_id!=order.configuracion_despliegue_id
            or service.asignacion_snapshot!=order.asignacion_snapshot):raise unavailable()
    row,document,profile=await validar_asignacion_aplicacion(db,order)
    allocation=await db.scalar(select(ReservaRedAplicacion).where(ReservaRedAplicacion.identidad_id==identity.id).execution_options(populate_existing=True))
    try:
        snapshot=allocation.snapshot
        instance=snapshot['instance']
        if (allocation.liberada_at is not None or allocation.cluster_id!=identity.cluster_id
                or identity.cluster_id!=get_settings().infrastructure_profile['cluster_id']
                or identity.nodo not in profile['nodes'] or identity.nodo!=order.destino_snapshot['nodo']
                or snapshot['resource_uuid']!=str(identity.resource_uuid)
                or allocation.perfil_id!=profile['network_profile_id']
                or snapshot['network_sha256']!=order.asignacion_snapshot['network_sha256']
                or (allocation.address,allocation.host,allocation.mac)!=(instance['address'],instance['host'],instance['mac_address'])
                or order.asignacion_snapshot['network_snapshot']['slots'][allocation.slot_id]!=
                    {key:instance[key] for key in ('address','host','mac_address')}):raise ValueError()
        port=8443 if document['access']['tipo']=='web' else document['access']['puerto']
        endpoint='https://'+instance['host']+':'+str(port) if document['access']['tipo']=='web' else instance['host']
        if prepared:
            metadata=service.acceso_metadata or {}
            nonce=configured_keyring().decrypt(identity.nonce_cifrado,context=f'infra:{identity.resource_uuid}:nonce')
            if (metadata.get('configuracion_sha256')!=row.sha256 or metadata.get('nonce_sha256')!=sha256(nonce.encode()).hexdigest()
                    or metadata.get('local_health') is not True or metadata.get('endpoint')!=endpoint
                    or metadata.get('host')!=instance['host'] or metadata.get('port')!=port
                    or metadata.get('addresses')!=[instance['address']]):raise ValueError()
        return identity,{**instance,'port':port,'endpoint':endpoint,'access':document['access'],
            'configuration_sha256':row.sha256,'configuration_id':str(row.id)}
    except (ValueError,KeyError,TypeError,AttributeError,SecretError):raise unavailable() from None
