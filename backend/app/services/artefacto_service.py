"""Artefactos construidos y sus réplicas; nunca se adoptan rutas del navegador."""
from sqlalchemy import select
from app.models.artefacto_preparado import ArtefactoPreparado,ReplicaArtefacto
from app.config import get_settings
from app.schemas.definicion import validar_manifest
from app.utils.errors import error
from app.utils.clock import clock


async def registrar(db,trial,result):
    from app.models.definicion_servicio import DefinicionServicio
    manifest=result['manifest'];validar_manifest(manifest,parcial=True)
    definition=await db.get(DefinicionServicio,trial.definicion_id)
    if (manifest.get('product')!='drawio' or manifest['definition_key']!=definition.codigo or manifest['definition_version']!=definition.version
        or any(type(result.get(k)) is not int or result[k]<=0 for k in ['image_bytes','bundle_bytes'])
        or result.get('saneamiento')!={'builder_sanitized':True}):
        raise error(409,'artefacto_incompatible','El resultado no acredita el artefacto esperado')
    profile=get_settings().perfiles_ensayo[trial.perfil_id]
    existing=await db.scalar(select(ArtefactoPreparado).where(ArtefactoPreparado.definicion_id==definition.id))
    if existing:
        if existing.manifest!=manifest:raise error(409,'artefacto_existente','No sustituir otro artefacto construido')
        return existing
    row=ArtefactoPreparado(definicion_id=definition.id,entradas_sha256=trial.entradas_sha256,
        registro_id=profile.builder_id,scope_id=get_settings().builder_hosts[profile.builder_id].scope_id,
        volume_id=manifest['image']['volume_id'],image_sha256=manifest['image']['sha256'],image_bytes=result['image_bytes'],
        bundle_sha256=manifest['preparation']['bundle_sha256'],bundle_bytes=result['bundle_bytes'],manifest=manifest,
        saneamiento=result['saneamiento'],estado='construyendo')
    db.add(row);await db.flush()
    from app.models.reserva_espacio_builder import ReservaEspacioBuilder
    reservation=await db.scalar(select(ReservaEspacioBuilder).where(ReservaEspacioBuilder.ensayo_id==trial.id).with_for_update())
    retained=row.image_bytes+row.bundle_bytes
    if not reservation or retained>reservation.bytes_temporales+reservation.bytes_finales_previstos:
        raise error(409,'presupuesto_artefacto_excedido','El artefacto excede el presupuesto reservado; conservar para revisión')
    reservation.bytes_temporales=max(0,reservation.bytes_temporales-retained)
    reservation.bytes_finales_previstos=0
    trial.artefacto_id=row.id;return row


async def replicas(db,artifact,result):
    values=result.get('replicas',[])
    if not values:raise error(409,'replica_no_disponible','Faltan réplicas institucionales')
    for value in values:
        if value['image_sha256']!=artifact.image_sha256 or value['bundle_sha256']!=artifact.bundle_sha256:
            raise error(409,'replica_alterada','La réplica no coincide con la construcción')
        row=await db.scalar(select(ReplicaArtefacto).where(ReplicaArtefacto.artefacto_id==artifact.id,ReplicaArtefacto.nodo==value['nodo'],ReplicaArtefacto.storage_id==value['storage_id']))
        if row:
            row.registro_revision=value['registro_revision'];row.verified_at=clock.now()
        else:db.add(ReplicaArtefacto(artefacto_id=artifact.id,**value))
    artifact.estado='disponible'
