"""Catálogo de versiones inmutables; publicar requiere evidencia y artefactos."""
from copy import deepcopy
from datetime import datetime
import hashlib
import ipaddress
import os
from pathlib import Path
import re
import stat
from uuid import UUID

from sqlalchemy import select, text

from app.config import get_settings
from app.models.definicion_servicio import DefinicionServicio
from app.models.evento_seguridad import EventoSeguridad
from app.models.pedido import Pedido
from app.models.servicio import Servicio
from app.models.usuario import RolUsuario
from app.schemas.definicion import DefinicionCreate, validar_manifest, digest
from app.services.acceso_service import usuario_actual, requiere_admin_actual, catedras_visibles
from app.services.idempotencia_service import ejecutar, ResultadoDecision
from app.services import evidencia_service, infraestructura_io
from app.utils.clock import clock, db_utc
from app.utils.errors import error


def presentar(row, *, tecnico=False):
    result = {key: getattr(row, key) for key in ['codigo', 'version', 'producto', 'modelo_servicio', 'estado']}
    result['id'] = str(row.id)
    result['minimum_resources'] = (row.manifest or {}).get('minimum_resources')
    result['allowed_parameters'] = (row.manifest or {}).get('allowed_parameters', [])
    if tecnico:
        result.update(manifest=row.manifest, manifest_sha256=row.manifest_sha256,
            evidencia_validacion=str(row.evidencia_validacion) if row.evidencia_validacion else None)
    return result


async def listar(db, *, actor, modelo=None, incluir_no_publicadas=False):
    actor = await usuario_actual(db, actor)
    query = select(DefinicionServicio)
    if actor.rol != RolUsuario.ADMIN or not incluir_no_publicadas:
        query = query.where(DefinicionServicio.estado == 'publicada')
    if modelo:
        query = query.where(DefinicionServicio.modelo_servicio == modelo)
    return [presentar(row, tecnico=actor.rol == RolUsuario.ADMIN) for row in (await db.scalars(query.order_by(DefinicionServicio.codigo, DefinicionServicio.version))).all()]


async def obtener(db, identity, *, actor):
    actor = await usuario_actual(db, actor)
    row = await db.get(DefinicionServicio, identity, populate_existing=True)
    if not row:
        raise error(404, 'definicion_no_encontrada', 'Definición no encontrada')
    if actor.rol != RolUsuario.ADMIN and row.estado != 'publicada':
        visible = await catedras_visibles(db, actor)
        # Una referencia aprobada conserva su lectura aun retirada; un pedido
        # meramente solicitado no permite explorar borradores o infraestructura.
        referred = await db.scalar(select(Pedido.id).where(Pedido.catedra_id.in_(visible),
            Pedido.definicion_version_id == row.id, Pedido.revision_decision > 0).limit(1))
        delivered = await db.scalar(select(Servicio.id).where(Servicio.catedra_id.in_(visible),
            Servicio.definicion_version_id == row.id).limit(1))
        if not referred and not delivered:
            raise error(403, 'sin_permisos', 'La definición no está disponible para esta cátedra')
    return presentar(row, tecnico=actor.rol == RolUsuario.ADMIN)


async def crear(db, *, actor, data, clave):
    actor = await requiere_admin_actual(db, actor)
    data = data if isinstance(data, DefinicionCreate) else DefinicionCreate.model_validate(data)
    async def decide(session):
        if session.bind.dialect.name == 'postgresql':
            lock = int.from_bytes(hashlib.sha256(f'definicion:{data.codigo}:{data.version}'.encode()).digest()[:8], signed=True)
            await session.execute(text('SELECT pg_advisory_xact_lock(:lock)'), {'lock': lock})
        duplicate = await session.scalar(select(DefinicionServicio.id).where(DefinicionServicio.codigo == data.codigo, DefinicionServicio.version == data.version))
        if duplicate:
            raise error(409, 'version_existente', 'Ese código y versión ya están registrados')
        row = DefinicionServicio(**data.model_dump(), manifest={})
        session.add(row)
        await session.flush()
        session.add(EventoSeguridad(actor_usuario_id=actor.id, accion='crear_definicion', resultado='completado', referencia=str(row.id)))
        return ResultadoDecision(201, presentar(row, tecnico=True))
    return await ejecutar(db, actor_id=actor.id, clave=clave, metodo='POST', ruta='/definiciones',
        payload=data.model_dump(), decidir=decide)


async def guardar_manifest(db, identity, *, actor, manifest, clave):
    actor = await requiere_admin_actual(db, actor)
    validar_manifest(manifest, parcial=True)
    async def decide(session):
        row = await _locked(session, identity)
        if row.estado != 'borrador':
            raise error(409, 'version_inmutable', 'La versión validada es inmutable; creá otra versión')
        for name, expected in [('definition_key', row.codigo), ('definition_version', row.version),
            ('product', row.producto), ('service_model', row.modelo_servicio), ('resource_type', 'lxc')]:
            if name in manifest and manifest[name] != expected:
                raise error(422, 'manifiesto_incompatible', 'El manifiesto corresponde a otro producto o versión')
        row.manifest = deepcopy(manifest)
        await session.flush()
        return ResultadoDecision(200, presentar(row, tecnico=True))
    return await ejecutar(db, actor_id=actor.id, clave=clave, metodo='PUT', ruta=f'/definiciones/{identity}/manifest', payload={'manifest': manifest}, decidir=decide)


async def _locked(db, identity):
    row = await db.scalar(select(DefinicionServicio).where(DefinicionServicio.id == identity).with_for_update().execution_options(populate_existing=True))
    if not row:
        raise error(404, 'definicion_no_encontrada', 'Definición no encontrada')
    return row


async def comprobar_evidencia(db, row):
    validar_manifest(row.manifest)
    value = row.manifest
    if (value['definition_key'], value['definition_version'], value['product'], value['service_model']) != (row.codigo, row.version, row.producto, row.modelo_servicio):
        raise error(409, 'manifiesto_incompatible', 'La identidad del manifiesto no coincide')
    proof = value['validation']
    entry, document = await evidencia_service.obtener(db, UUID(proof['evidence_id']), tipo='validacion_definicion', revalidar=True)
    result = document['resultado']
    if (result['definicion_id'] != str(row.id) or entry.sha256 != proof['evidence_sha256']
        or result['image_sha256'] != value['image']['sha256'] or result['recipe_sha256'] != value['preparation']['bundle_sha256']
        or result['cluster_uuid'] != proof['cluster_uuid'] or sorted(result['pve_versions']) != sorted(proof['pve_versions'])
        or len(result['instancias']) != proof['instances_tested'] or set(result['checks']) != set(proof['checks'])
        or datetime.fromisoformat(document['observado_at'].replace('Z', '+00:00')) != datetime.fromisoformat(proof['validated_at'].replace('Z', '+00:00'))):
        raise error(409, 'evidencia_desactualizada', 'La evidencia no coincide con el manifiesto construido')
    if document['entorno'] != 'real' and get_settings().app_env != 'test':
        raise error(422, 'evidencia_simulada', 'Publicar requiere evidencia institucional real')
    if row.manifest_sha256 and row.manifest_sha256 != digest(value):
        raise error(409, 'manifiesto_alterado', 'El contenido de la versión validada cambió')
    return entry


def hash_archivo_controlado(path):
    value = Path(path)
    if not value.is_absolute() or value.resolve() != value:
        raise ValueError('Ruta de artefacto no controlada')
    fd = os.open(value, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_mode & 0o022 or before.st_uid not in {0, os.geteuid()}:
            raise ValueError('Artefacto no controlado')
        checksum = hashlib.sha256()
        with os.fdopen(fd, 'rb', closefd=False) as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b''):
                checksum.update(chunk)
        after = os.fstat(fd)
        if (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError('Artefacto modificado durante lectura')
        return checksum.hexdigest()
    finally:
        os.close(fd)


async def comprobar_disponibilidad(manifest, *, pve=None):
    """Registro de infraestructura montado, nunca rutas recibidas desde la API.

    El operador conserva imagen/bundle y prepara el runner según T101. Aquí se
    comprueban sus archivos, perfiles y disponibilidad PVE antes de habilitar.
    """
    settings = get_settings()
    registry = settings.service_artifacts.get(manifest['definition_key'] + ':' + manifest['definition_version'])
    profiles = settings.network_profiles
    if (not registry or settings.infrastructure_profile.get('cluster_id') != manifest['validation']['cluster_uuid']
        or not registry.get('nodes') or any(node not in settings.runner_nodes for node in registry['nodes'])
        or any(key not in profiles for key in manifest['network_profile_ids'])):
        raise error(409, 'preparacion_no_disponible', 'Faltan artefactos, perfiles o runner institucional comprobado')
    try:
        for profile_id in manifest['network_profile_ids']:
            profile = profiles[profile_id]
            if (not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,14}', profile.get('bridge', ''))
                or not set(registry['nodes']) <= set(profile.get('nodes', []))
                or not profile.get('allowed_cidrs') or not profile.get('client_cidrs')
                or ('vlan_tag' in profile and (type(profile['vlan_tag']) is not int or not 1 <= profile['vlan_tag'] <= 4094))):
                raise ValueError('Perfil de red incompleto')
            for cidr in profile['allowed_cidrs'] + profile['client_cidrs']:
                if ipaddress.ip_network(cidr).prefixlen == 0:
                    raise ValueError('Red sin delimitación')
        for field, expected in [('image_path', manifest['image']['sha256']), ('bundle_path', manifest['preparation']['bundle_sha256'])]:
            actual = await infraestructura_io.ejecutar(hash_archivo_controlado, registry[field], timeout=180)
            if actual != expected:
                raise error(409, 'artefacto_alterado', 'El digest del artefacto instalado no coincide')
        volume = manifest['image']['volume_id']
        storage = volume.split(':', 1)[0]
        def available(client):
            nodes = {entry['node'] for entry in client.get_nodes() if entry.get('status') == 'online'}
            for node in registry['nodes']:
                if node not in nodes or not any(item.get('volid') == volume for item in client.get_storage_content(node, storage)):
                    return False
            return True
        if not await infraestructura_io.con_cliente(available, pve=pve):
            raise error(409, 'imagen_no_disponible', 'La imagen validada no está disponible en los nodos autorizados')
    except (KeyError, OSError, ValueError, infraestructura_io.InfraNoVerificable):
        raise error(502, 'artefacto_no_verificable', 'No se pudo comprobar la imagen o receta institucional') from None


async def transicionar(db, identity, *, actor, accion, payload, clave):
    actor = await requiere_admin_actual(db, actor)
    async def decide(session):
        row = await _locked(session, identity)
        allowed = {'validar': {'borrador'}, 'publicar': {'validada'}, 'retirar': {'validada', 'publicada'}}
        if accion not in allowed or row.estado not in allowed[accion]:
            raise error(409, 'estado_incompatible', 'La versión no admite esa transición')
        if accion in {'validar', 'publicar'}:
            entry = await comprobar_evidencia(session, row)
            await comprobar_disponibilidad(deepcopy(row.manifest))
            if accion == 'validar':
                row.manifest_sha256, row.evidencia_validacion = digest(row.manifest), entry.id
                row.validada_at, row.validada_por = clock.now(), actor.id
            row.estado = 'validada' if accion == 'validar' else 'publicada'
        else:
            row.estado, row.retirada_at = 'retirada', clock.now()
        session.add(EventoSeguridad(actor_usuario_id=actor.id, accion=accion + '_definicion', resultado='completado',
            motivo=payload.get('motivo'), referencia=str(row.id)))
        await session.flush()
        return ResultadoDecision(200, presentar(row, tecnico=True))
    return await ejecutar(db, actor_id=actor.id, clave=clave, metodo='POST', ruta=f'/definiciones/{identity}/{accion}', payload=payload, decidir=decide)
