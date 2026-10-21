"""Disponibilidad del perfil y su definición; sin parámetros PVE del docente."""
from sqlalchemy import select

from app.models.definicion_servicio import DefinicionServicio
from app.models.recurso_template import TipoRecurso
from app.schemas.definicion import digest
from app.services.catalogo_service import comprobar_evidencia
from app.utils.errors import error


def compatible(template, definition):
    if (not definition or template.tipo != TipoRecurso.LXC or not template.activo
        or definition.estado != 'publicada' or definition.modelo_servicio != template.modelo_servicio.value
        or not definition.manifest_sha256 or definition.manifest_sha256 != digest(definition.manifest)
        or not definition.evidencia_validacion):
        return False
    minimum = definition.manifest.get('minimum_resources', {})
    image = definition.manifest.get('image', {}).get('volume_id')
    return bool(image and template.os_template in (None, image) and all(
        key in minimum and getattr(template, field) >= minimum[key]
        for field, key in [('default_vcpus', 'vcpus'), ('default_ram_mb', 'ram_mb'), ('default_disk_gb', 'disk_gb')]))


async def exigir_definicion(db, template, *, bloquear=False):
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
        row.oferta_disponible = compatible(row, definitions.get(row.definicion_version_id))
    return templates
