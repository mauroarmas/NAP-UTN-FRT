"""Registro inmutable. El hash comprueba integridad, no firma una observación."""

from datetime import datetime
import hashlib
import hmac
import json
from uuid import UUID

from sqlalchemy import select

from app.config import get_settings
from app.models.cambio_acceso_consola import CambioAccesoConsola
from app.models.definicion_servicio import DefinicionServicio
from app.models.evidencia import Evidencia
from app.models.identidad_infraestructura import IdentidadInfraestructura
from app.models.operacion_infraestructura import OperacionInfraestructura
from app.models.servicio import Servicio
from app.schemas.evidencia import canonical
from app.services.idempotencia_service import ejecutar, ResultadoDecision
from app.utils.clock import clock, db_utc
from app.utils.errors import error
from app.utils.secretos import configured_keyring, SecretError

BASE_CHECKS = {'image_digest', 'sanitized_image', 'repeatable_deployment', 'bootstrap_idempotence',
               'functional_access', 'student_network_access', 'persistence_after_restart', 'cross_instance_isolation'}


async def _locked(db, model, identity):
    return await db.scalar(select(model).where(model.id == identity).with_for_update().execution_options(populate_existing=True))


async def validar_destino(db, document):
    try:
        observed = datetime.fromisoformat(document['observado_at'].replace('Z', '+00:00'))
    except ValueError:
        raise error(422, 'evidencia_invalida', 'Instante de observación inválido') from None
    if observed > clock.now():
        raise error(422, 'evidencia_invalida', 'La observación no puede estar en el futuro')
    if document['entorno'] == 'simulado' and get_settings().app_env != 'test':
        raise error(422, 'evidencia_simulada', 'La aceptación operativa requiere evidencia real')
    data = document['resultado']
    kind = document['tipo']
    if kind == 'validacion_definicion':
        definition = await _locked(db, DefinicionServicio, UUID(data['definicion_id']))
        if definition is None:
            raise error(422, 'evidencia_invalida', 'Definición no registrada')
        if (definition.codigo, definition.version) != (data['definition_key'], data['definition_version']):
            raise error(409, 'evidencia_desactualizada', 'La evidencia corresponde a otra versión')
        required = BASE_CHECKS | ({'unique_secrets'} if definition.producto in {'postgresql', 'bookstack'} else set())
        if definition.producto == 'bookstack':
            required.add('reader_permissions_and_revocation')
        if not required <= set(data['checks']):
            raise error(422, 'evidencia_invalida', 'Faltan pruebas funcionales del producto')
        image = definition.manifest.get('image', {}).get('sha256')
        bundle = definition.manifest.get('preparation', {}).get('bundle_sha256')
        if (image and image != data['image_sha256']) or (bundle and bundle != data['recipe_sha256']):
            raise error(409, 'evidencia_desactualizada', 'Los artefactos ya no coinciden')
    elif kind == 'revocacion_consola':
        change = await _locked(db, CambioAccesoConsola, UUID(data['cambio_consola_id']))
        if change is None:
            raise error(422, 'evidencia_invalida', 'Trámite no registrado')
        if (change.revision_esperada != data['revision_esperada']
            or change.identidad_nativa != data['identidad_nativa']
            or sorted(change.scopes_propuestos) != sorted(data['scopes_resultantes'])
            or change.estado not in {'pendiente', 'revocacion_fallida'}
            or observed < db_utc(change.solicitada_at)):
            raise error(409, 'evidencia_desactualizada', 'La evidencia no corresponde al trámite vigente')
    else:
        service = await _locked(db, Servicio, data['servicio_id'])
        if service is None or service.deleted_at is not None:
            raise error(422, 'evidencia_invalida', 'Instancia no registrada')
        identity = await _locked(db, IdentidadInfraestructura, service.identidad_infraestructura_id) if service.identidad_infraestructura_id else None
        operation = await _locked(db, OperacionInfraestructura, UUID(data['preparacion_id']))
        latest = await db.scalar(select(OperacionInfraestructura).where(
            OperacionInfraestructura.servicio_id == service.id,
            OperacionInfraestructura.tipo.in_(['desplegar', 'reparar']),
        ).order_by(OperacionInfraestructura.creado_at.desc(), OperacionInfraestructura.id.desc()).limit(1))
        if (identity is None or operation is None or latest is None or latest.id != operation.id
            or str(identity.resource_uuid) != data['resource_uuid']
            or str(service.definicion_version_id) != data['definicion_id']
            or operation.servicio_id != service.id or operation.estado != 'confirmada'
            or operation.confirmada_at is None or observed < db_utc(operation.confirmada_at)
            or (service.acceso_metadata or {}).get('endpoint') != data['endpoint']):
            raise error(409, 'evidencia_desactualizada', 'Instancia, preparación o endpoint no vigentes')
        try:
            nonce = configured_keyring().decrypt(identity.nonce_cifrado, context=f'infra:{identity.resource_uuid}:nonce')
            digest = hashlib.sha256(nonce.encode()).hexdigest()
        except (SecretError, AttributeError):
            raise error(409, 'evidencia_desactualizada', 'No se pudo contrastar la identidad preparada') from None
        if not hmac.compare_digest(digest, data['nonce_sha256']):
            raise error(409, 'evidencia_desactualizada', 'Identidad de instancia no coincidente')
        definition = await db.get(DefinicionServicio, service.definicion_version_id)
        required = {'linux': {'login_consola', 'sudo_local'},
                    'postgresql': {'conexion_autenticada', 'escritura_lectura', 'persistencia'},
                    'bookstack': {'publicacion_docente', 'lectura_individual', 'persistencia',
                        'permisos_lectores', 'revocacion_individual', 'archivos_privados'}}
        if definition is None or not required.get(definition.producto, {'producto_no_soportado'}) <= set(data['pruebas']):
            raise error(422, 'evidencia_invalida', 'La prueba no cubre la función del producto')


async def registrar(db, document, *, usuario, clave):
    async def decide(session):
        await validar_destino(session, document)
        encoded = canonical(document)
        entry = Evidencia(tipo=document['tipo'], schema_version=1, documento_canonico=encoded,
                          sha256=hashlib.sha256(encoded.encode()).hexdigest(), registrada_por=usuario.id)
        session.add(entry)
        await session.flush()
        return ResultadoDecision(201, {'evidencia_ref': str(entry.id), 'sha256': entry.sha256,
            'tipo': entry.tipo, 'registrada_por': usuario.id,
            'registrada_at': db_utc(entry.registrada_at).isoformat().replace('+00:00', 'Z')})

    return await ejecutar(db, actor_id=usuario.id, clave=clave, metodo='POST', ruta='/evidencias',
                          payload=document, decidir=decide)


async def obtener(db, identity, *, tipo=None, revalidar=False):
    entry = await db.get(Evidencia, identity, populate_existing=True)
    if entry is None:
        raise error(404, 'evidencia_no_encontrada', 'Evidencia no registrada')
    digest = hashlib.sha256(entry.documento_canonico.encode()).hexdigest()
    if not hmac.compare_digest(digest, entry.sha256):
        raise error(409, 'evidencia_alterada', 'La integridad de la evidencia no coincide')
    document = json.loads(entry.documento_canonico)
    if document['tipo'] != entry.tipo or (tipo and entry.tipo != tipo):
        raise error(422, 'tipo_evidencia_incompatible', 'La evidencia no corresponde a esta acción')
    if revalidar:
        await validar_destino(db, document)
    return entry, document
