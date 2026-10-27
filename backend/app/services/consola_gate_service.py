"""Compuerta institucional explícita; un archivo o una URL no acreditan ACL."""
from uuid import UUID
from datetime import datetime

from sqlalchemy import select
from app.config import get_settings
from app.models.cambio_acceso_consola import CambioAccesoConsola
from app.models.identidad_infraestructura import IdentidadInfraestructura
from app.models.catedra import Catedra
from app.models.usuario import Usuario
from app.schemas.evidencia import parse_document
from app.services.evidencia_service import obtener
from app.services.acceso_service import usuario_actual, catedras_visibles
from app.utils.clock import clock, db_utc
from app.utils.errors import error


async def exigir_gate(db, service):
    settings = get_settings()
    profile = settings.console_access_profile
    try:
        cluster = settings.infrastructure_profile['cluster_id']
        if profile['cluster_uuid'] != cluster or not profile['pve_version']:
            raise ValueError()
        proof, _ = await obtener(db, UUID(profile['gate']['evidencia_ref']), tipo='revocacion_consola')
        document = parse_document(proof.documento_canonico.encode())
        result = document['resultado']
        change = await db.get(CambioAccesoConsola, UUID(result['cambio_consola_id']))
        observed = datetime.fromisoformat(document['observado_at'].replace('Z', '+00:00'))
        if (proof.sha256 != profile['gate']['sha256'] or document['entorno'] != 'real'
            or result.get('cluster_uuid') != cluster or result.get('pve_version') != profile['pve_version']
            or observed > clock.now() or not change or change.estado != 'completado'
            or change.evidencia_id != proof.id or not change.completada_at
            or observed < db_utc(change.solicitada_at) or observed > db_utc(change.completada_at)
            or change.identidad_nativa != result['identidad_nativa']
            or change.revision_esperada != result['revision_esperada']
            or sorted(change.scopes_propuestos) != sorted(result['scopes_resultantes'])):
            raise ValueError()
        identity = await db.get(IdentidadInfraestructura, service.identidad_infraestructura_id) if service.identidad_infraestructura_id else None
        if (not identity or identity.cluster_id != cluster or identity.servicio_id != service.id
            or identity.estado != 'materializada' or not identity.ownership_verificada_at or identity.ausencia_confirmada_at
            or identity.pool_catedra != f'catedra-{service.catedra_id}'
            or str(identity.vmid) != service.proxmox_vmid or identity.nodo != service.proxmox_node):
            raise ValueError()
        return profile
    except Exception as exc:
        if getattr(exc, 'status_code', None) == 403:
            raise
        raise error(409, 'consola_no_habilitada',
            'Falta acreditar aislamiento, identidad y revocación de consola para esta instalación') from None


async def autorizar(db, service, actor):
    actor = await usuario_actual(db, actor)
    profile = await exigir_gate(db, service)
    try:
        grant = profile['identities'][actor.identidad_consola]
        if (actor.inventario_consola != 'asignada' or not actor.inventario_consola_actor
            or not actor.inventario_consola_ref or grant['usuario_id'] != actor.id
            or grant['revision_admin'] != actor.revision_admin or not grant['referencia_institucional']):
            raise ValueError()
        owners = (await db.scalars(select(Usuario.id).where(
            Usuario.identidad_consola == actor.identidad_consola))).all()
        if owners != [actor.id]:
            raise ValueError()
        visible = await catedras_visibles(db, actor)
        scopes = grant['catedras']
        if str(service.catedra_id) not in scopes:
            raise ValueError()
        for key, revision in scopes.items():
            category = await db.get(Catedra, int(key), populate_existing=True)
            if int(key) not in visible or not category or category.revision_admin != revision:
                raise ValueError()
    except (KeyError, TypeError, ValueError, AttributeError):
        raise error(409, 'consola_no_habilitada', 'Falta acreditar la identidad nativa individual y sus pools actuales') from None
