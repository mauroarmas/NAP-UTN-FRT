"""Alta guiada: decisiones del administrador, detalles técnicos resueltos por NAP."""
import hashlib
from uuid import UUID
from sqlalchemy import select

from app.config import get_settings
from app.models.artefacto_preparado import ArtefactoPreparado, ReplicaArtefacto
from app.models.definicion_servicio import DefinicionServicio
from app.models.ensayo_preparacion import EnsayoPreparacion
from app.models.identidad_infraestructura import IdentidadInfraestructura
from app.models.recurso_ensayo import RecursoEnsayo
from app.models.recurso_template import RecursoTemplate
from app.models.operacion_ensayo import OperacionEnsayo
from app.schemas.ensayo import EnsayoCreate, RevisionBiblioteca, ComprobarEnsayo, DescartarEnsayo, PublicarOferta, PerfilOferta
from app.schemas.preparacion_simple import SIMPLE_CHECKS
from app.schemas.definicion import digest
from app.schemas.evidencia import parse_document, canonical
from app.schemas.tamanos import TAMANOS
from app.services import biblioteca_service, ensayo_service, catalogo_service, evidencia_service, infraestructura_io, capacidad_service
from app.services.acceso_service import requiere_admin_actual
from app.services.idempotencia_service import ejecutar, ResultadoDecision
from app.utils.clock import clock
from app.utils.errors import error
from app.utils.secretos import configured_keyring


def subclave(clave, paso):
    return 'alta-simple:' + paso + ':' + hashlib.sha256(clave.encode()).hexdigest()


def perfil_automatico():
    settings = get_settings()
    profiles = [(key, value) for key, value in settings.perfiles_ensayo.items()
                if value.builder_id in settings.builder_hosts and value.network_profile_id in settings.network_profiles]
    return min(profiles, key=lambda item: (item[1].ram_mb, item[1].vcpus, item[1].disk_gb, item[0]))[0] if profiles else None


async def actual(db, identity, actor, *, bloquear=False):
    inc = await biblioteca_service.obtener(db, identity, actor=actor, bloquear=bloquear)
    definition = await db.scalar(select(DefinicionServicio).where(DefinicionServicio.incorporacion_id == inc.id)
                                 .order_by(DefinicionServicio.created_at.desc(), DefinicionServicio.id.desc()).limit(1).execution_options(populate_existing=True))
    trial = await db.scalar(select(EnsayoPreparacion).where(EnsayoPreparacion.definicion_id == definition.id)
                           .order_by(EnsayoPreparacion.creado_at.desc()).limit(1).execution_options(populate_existing=True)) if definition else None
    return inc, definition, trial


async def estado(db, identity, *, actor):
    inc, definition, trial = await actual(db, identity, actor)
    supported = inc.identidad_externa == 'ct/drawio.sh'
    configured = bool(perfil_automatico())
    result = {'nombre': inc.nombre, 'estado': 'sin_preparar', 'mensaje': '',
              'puede_preparar': supported and configured, 'preparacion_id': str(trial.id) if trial else None,
              'minimum_resources': (definition.manifest or {}).get('minimum_resources') if definition else None,
              'recursos': [], 'datos_servicio': None}
    if not supported:
        result['mensaje'] = 'Esta aplicación todavía no se puede preparar desde NAP.'
    elif not configured:
        result['mensaje'] = 'Falta completar la conexión con Proxmox. Debe configurarla el responsable técnico una sola vez.'
    if not trial:
        return result
    initial = await db.scalar(select(OperacionEnsayo).where(OperacionEnsayo.ensayo_id == trial.id, OperacionEnsayo.tipo == 'resolver').order_by(OperacionEnsayo.created_at).limit(1))
    if initial:
        result['datos_servicio'] = initial.contexto_seguro.get('oferta')
    result['puede_preparar'] = False
    result['estado'] = 'preparando'
    if trial.publicacion_id:
        result['estado'] = 'publicada'
    elif trial.cancelada_at:
        result['estado'] = 'eliminada' if trial.limpieza_estado == 'confirmada' else 'eliminando'
        if result['estado'] == 'eliminada':
            result['puede_preparar'] = supported and configured
    elif trial.estado in {'fallida', 'incierta'}:
        result['estado'] = 'fallida'
        result['mensaje'] = 'No se pudo completar la preparación. Podés eliminarla y volver a empezar.'
    elif trial.estado == 'lista_para_comprobar':
        result['estado'] = 'lista_para_probar'
    elif trial.estado == 'comprobada':
        replicas = list((await db.scalars(select(ReplicaArtefacto).where(ReplicaArtefacto.artefacto_id == trial.artefacto_id).execution_options(populate_existing=True))).all())
        if replicas and all(row.registro_revision == digest(definition.manifest) for row in replicas):
            result['estado'] = 'lista_para_publicar'
    if result['estado'] == 'lista_para_probar':
        resources = list((await db.scalars(select(RecursoEnsayo).where(RecursoEnsayo.ensayo_id == trial.id,
            RecursoEnsayo.ausencia_confirmada_at.is_(None)).order_by(RecursoEnsayo.rol))).all())
        result['recursos'] = [{'id': str(row.id)} for row in resources if row.acceso_metadata.get('local_health')][:1]
    if result['estado'] in {'preparando', 'lista_para_probar', 'lista_para_publicar', 'publicada', 'eliminada', 'eliminando'}:
        result['mensaje'] = ''
    return result


async def preparar(db, identity, *, actor, clave, data=None, pve=None, builder=None):
    actor = await requiere_admin_actual(db, actor)
    async def decide(session):
        inc, definition, trial = await actual(session, identity, actor, bloquear=True)
        if trial and (not trial.cancelada_at or trial.limpieza_estado != 'confirmada'):
            return ResultadoDecision(200, await estado(session, identity, actor=actor))
        profile = perfil_automatico()
        if not profile:
            raise error(409, 'infraestructura_no_configurada', 'Falta completar la conexión con Proxmox. Contactá al responsable técnico.')
        if inc.identidad_externa != 'ct/drawio.sh':
            raise error(409, 'adaptador_no_disponible', 'Esta aplicación todavía no se puede preparar desde NAP.')
        if definition is None or trial is not None:
            version = '1.0.0' if definition is None else '.'.join(map(str, [int(definition.version.split('.')[0]) + 1, 0, 0]))
            code = definition.codigo if definition else 'drawio-' + inc.id.hex[:12]
            result = await ensayo_service.crear_revision(session, identity, actor=actor,
                data=RevisionBiblioteca(revision_esperada=inc.revision, codigo=code, version=version,
                                        base_definicion_id=definition.id if definition else None), clave=subclave(clave, 'version'))
            definition = await session.get(DefinicionServicio, UUID(result.resultado['id']))
        started = await ensayo_service.iniciar(session, definition.id, actor=actor,
            data=EnsayoCreate(incorporacion_id=inc.id, revision_esperada=definition.revision,
                             perfil_ensayo_id=profile, plazo_horas=None), clave=subclave(clave, 'inicio'), pve=pve, builder=builder)
        if data:
            initial = await session.scalar(select(OperacionEnsayo).where(OperacionEnsayo.ensayo_id == UUID(started.resultado['id']), OperacionEnsayo.tipo == 'resolver'))
            initial.contexto_seguro = {**initial.contexto_seguro, 'oferta': {'nombre': data.nombre or inc.nombre,
                'descripcion': data.descripcion, 'tamano': data.tamano}}
            await session.flush()
        return ResultadoDecision(202, await estado(session, identity, actor=actor))
    return await ejecutar(db, actor_id=actor.id, clave=clave, metodo='POST',
        ruta=f'/biblioteca/incorporaciones/{identity}/preparar', payload=data.model_dump() if data else {}, decidir=decide)


async def validar_evidencia_simple(db, definition, data):
    """Comprueba el origen real; no atribuye ensayos de restauración/exportación que no se hicieron."""
    trial = await db.scalar(select(EnsayoPreparacion).where(EnsayoPreparacion.definicion_id == definition.id,
        EnsayoPreparacion.expires_at.is_(None)).order_by(EnsayoPreparacion.creado_at.desc()).limit(1))
    if definition.producto != 'drawio' or not trial or trial.estado not in {'lista_para_comprobar', 'comprobada'}:
        raise error(422, 'comprobacion_invalida', 'Falta una preparación completada por NAP.')
    artifact = await db.get(ArtefactoPreparado, trial.artefacto_id) if trial.artefacto_id else None
    resources = list((await db.scalars(select(RecursoEnsayo).where(RecursoEnsayo.ensayo_id == trial.id))).all())
    if not artifact or artifact.saneamiento != {'builder_sanitized': True} or len(resources) != 2 or not all(row.credenciales_encrypted for row in resources):
        raise error(409, 'preparacion_incompleta', 'La preparación todavía no terminó.')
    identities = [await db.get(IdentidadInfraestructura, row.identidad_infraestructura_id) if row.identidad_infraestructura_id else None for row in resources]
    if (any(row is None for row in identities) or not all(row.acceso_metadata.get('local_health') for row in resources)
        or set(data['instancias']) != {str(row.resource_uuid) for row in identities}
        or any(row.definition_sha256 != digest(artifact.manifest) or row.bundle_sha256 != artifact.bundle_sha256 for row in identities)
        or artifact.image_sha256 != data['image_sha256'] or artifact.bundle_sha256 != data['recipe_sha256']
        or {row.cluster_id for row in identities} != {data['cluster_uuid']}
        or not SIMPLE_CHECKS <= set(data['checks'])):
        raise error(409, 'preparacion_incompleta', 'No se pudo comprobar la preparación de la aplicación.')
    passwords = [configured_keyring().decrypt(row.credenciales_encrypted, context=f'ensayo:{row.id}:secretos')['access_password'] for row in resources]
    if len(set(passwords)) != len(passwords):
        raise error(409, 'credenciales_no_independientes', 'La preparación necesita credenciales independientes.')


async def confirmar(db, identity, *, actor, funciona, clave, pve=None):
    actor = await requiere_admin_actual(db, actor)
    if not funciona:
        return await eliminar(db, identity, actor=actor, clave=clave)
    async def decide(session):
        inc, definition, trial = await actual(session, identity, actor, bloquear=True)
        if not trial or trial.estado != 'lista_para_comprobar' or trial.cancelada_at or trial.expires_at is not None:
            raise error(409, 'preparacion_no_lista', 'Esperá a que termine la preparación antes de probarla.')
        from app.services.identidad_infra_service import observar
        resources = list((await session.scalars(select(RecursoEnsayo).where(RecursoEnsayo.ensayo_id == trial.id))).all())
        if len(resources) != 2 or not trial.artefacto_id:
            raise error(409, 'preparacion_incompleta', 'La preparación todavía no terminó.')
        identities = []
        for resource in resources:
            native = await session.get(IdentidadInfraestructura, resource.identidad_infraestructura_id)
            if not native or resource.ausencia_confirmada_at:
                raise error(409, 'preparacion_no_lista', 'La preparación ya no está disponible.')
            observation = await observar(native, pve=pve)
            status = await infraestructura_io.consultar('get_lxc_status', native.nodo, native.vmid, pve=pve)
            if observation.estado != 'propia' or status.estado != 'presente' or status.valor.get('status') != 'running':
                raise error(409, 'aplicacion_no_disponible', 'La aplicación no está disponible. Revisá su conexión antes de confirmar.')
            identities.append(native)
        version = await infraestructura_io.consultar('get_version', pve=pve)
        if version.estado != 'presente' or not version.valor.get('version'):
            raise error(502, 'conexion_no_verificable', 'No se pudo consultar la conexión con Proxmox.')
        artifact = await session.get(ArtefactoPreparado, trial.artefacto_id)
        if artifact is None:
            raise error(409, 'preparacion_incompleta', 'La preparación todavía no terminó.')
        document = {'schema_version': 1, 'tipo': 'validacion_definicion', 'entorno': 'real',
            'operador_institucional': actor.nombre, 'referencia_institucional': 'NAP-preparacion-simple:' + str(trial.id),
            'observado_at': clock.now().isoformat().replace('+00:00', 'Z'), 'resultado': {
                'definicion_id': str(definition.id), 'definition_key': definition.codigo, 'definition_version': definition.version,
                'image_sha256': artifact.image_sha256, 'recipe_sha256': artifact.bundle_sha256,
                'cluster_uuid': get_settings().infrastructure_profile['cluster_id'], 'pve_versions': [version.valor['version']],
                'instancias': sorted(str(row.resource_uuid) for row in identities), 'checks': sorted(SIMPLE_CHECKS)}}
        parse_document(canonical(document).encode())
        await capacidad_service.BloqueoCapacidad(session).__aenter__()
        result = await evidencia_service.registrar(session, document, usuario=actor, clave=subclave(clave, 'comprobacion'))
        await ensayo_service.comprobar(session, trial.id, actor=actor,
            data=ComprobarEnsayo(revision_esperada=trial.revision, evidencia_id=result.resultado['evidencia_ref'],
                                evidencia_sha256=result.resultado['sha256']), clave=subclave(clave, 'confirmacion'))
        return ResultadoDecision(202, await estado(session, identity, actor=actor))
    return await ejecutar(db, actor_id=actor.id, clave=clave, metodo='POST',
        ruta=f'/biblioteca/incorporaciones/{identity}/confirmar-funcionamiento', payload={'funciona': funciona}, decidir=decide)


async def publicar(db, identity, *, actor, data, clave):
    actor = await requiere_admin_actual(db, actor)
    async def decide(session):
        inc, definition, trial = await actual(session, identity, actor, bloquear=True)
        if trial and trial.publicacion_id:
            return ResultadoDecision(200, await estado(session, identity, actor=actor))
        await capacidad_service.BloqueoCapacidad(session).__aenter__()
        if (await estado(session, identity, actor=actor))['estado'] != 'lista_para_publicar':
            raise error(409, 'preparacion_no_lista', 'Comprobá que la aplicación funcione antes de publicarla.')
        if not data.nombre.strip():
            raise error(422, 'nombre_requerido', 'Indicá el nombre del servicio.')
        if await session.scalar(select(RecursoTemplate.id).where(RecursoTemplate.nombre == data.nombre.strip())):
            raise error(409, 'nombre_existente', 'Ya hay un servicio con ese nombre. Elegí otro.')
        resources = TAMANOS[data.tamano]
        if any(resources[key] < definition.manifest['minimum_resources'][key] for key in resources):
            raise error(422, 'tamano_insuficiente', 'El tamaño elegido no alcanza para esta aplicación.')
        if definition.estado == 'borrador':
            await catalogo_service.transicionar(session, definition.id, actor=actor, accion='validar', payload={}, clave=subclave(clave, 'validacion'))
        await catalogo_service.publicar_oferta(session, definition.id, actor=actor,
            data=PublicarOferta(revision_esperada=definition.revision, ensayo_id=trial.id,
                perfil=PerfilOferta(nombre=data.nombre.strip(), descripcion=data.descripcion.strip(), tamano=data.tamano,
                                   **{'default_' + key: value for key, value in resources.items()})), clave=subclave(clave, 'oferta'))
        return ResultadoDecision(201, await estado(session, identity, actor=actor))
    return await ejecutar(db, actor_id=actor.id, clave=clave, metodo='POST',
        ruta=f'/biblioteca/incorporaciones/{identity}/publicar', payload=data.model_dump(), decidir=decide)


async def eliminar(db, identity, *, actor, clave):
    actor = await requiere_admin_actual(db, actor)
    async def decide(session):
        _, _, trial = await actual(session, identity, actor, bloquear=True)
        if trial and not trial.cancelada_at:
            await ensayo_service.accion(session, trial.id, actor=actor,
                data=DescartarEnsayo(revision_esperada=trial.revision, motivo='Eliminación solicitada por administración'),
                clave=subclave(clave, 'eliminar'), action='descartar')
        return ResultadoDecision(202, await estado(session, identity, actor=actor))
    return await ejecutar(db, actor_id=actor.id, clave=clave, metodo='POST',
        ruta=f'/biblioteca/incorporaciones/{identity}/eliminar', payload={}, decidir=decide)
