"""Preparación de snapshots aprobados, credenciales persistidas antes del envío."""
import base64
import hashlib
from copy import deepcopy
import re
import secrets
import time
from uuid import UUID

from app.config import get_settings
from app.models.definicion_servicio import DefinicionServicio
from app.models.usuario import Usuario
from app.schemas.guest_runner import PROTOCOL, RunnerError
from app.schemas.definicion import digest
from app.services import catalogo_service, probes_servicio
from app.services.guest_runner_client import GuestRunnerClient
from app.services.infraestructura_io import InfraNoVerificable
from app.utils.clock import clock, db_utc
from app.utils.errors import error
from app.utils.secretos import configured_keyring


async def _definition(db, assignment):
    try:
        row = await db.get(DefinicionServicio, UUID(assignment['definicion_version_id']))
        if not row or row.estado not in {'publicada', 'retirada'}:
            raise ValueError()
        await catalogo_service.comprobar_evidencia(db, row)
        manifest = row.manifest
        expected = {'definition_sha256': row.manifest_sha256, 'definition_key': row.codigo,
            'definition_version': row.version, 'product': row.producto, 'bundle_sha256': manifest['preparation']['bundle_sha256']}
        if (row.manifest_sha256 != digest(manifest) or any(assignment.get(key) != value for key, value in expected.items())
            or assignment.get('tipo') != 'lxc' or assignment.get('modelo_servicio') != row.modelo_servicio
            or assignment.get('image') != {'volume_id': manifest['image']['volume_id'], 'sha256': manifest['image']['sha256']}
            or any(type(assignment.get(key)) is not int or assignment[key] < minimum for key, minimum in manifest['minimum_resources'].items())):
            raise ValueError()
        return row
    except (KeyError, ValueError, TypeError, AttributeError):
        raise error(409, 'preparacion_no_disponible', 'El snapshot no acredita la definición, imagen y receta originales') from None


def _profile(manifest, destination, *, frozen=None):
    settings = get_settings()
    registry = settings.service_artifacts.get(manifest['definition_key'] + ':' + manifest['definition_version'])
    try:
        if not registry or registry.get('security_blocked') or destination['nodo'] not in registry['nodes']:
            raise ValueError()
        selected = frozen or registry['network_profile_id']
        profile = settings.network_profiles[selected]
        if (selected not in manifest['network_profile_ids'] or destination['nodo'] not in profile['nodes']
            or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,14}', profile['bridge'])):
            raise ValueError()
        tag = profile.get('vlan_tag')
        if tag is not None and (type(tag) is not int or not 1 <= tag <= 4094):
            raise ValueError()
        net0 = 'name=eth0,bridge=' + profile['bridge'] + ',ip=dhcp' + (f',tag={tag}' if tag is not None else '')
        return selected, deepcopy(profile), net0
    except (ValueError, KeyError, TypeError):
        raise error(409, 'red_no_preparada', 'Falta un perfil de red institucional autorizado') from None


async def validar_preparacion(*, sessions, asignacion, destino, runner=None, pve=None):
    async with sessions() as db:
        definition = await _definition(db, asignacion)
        manifest = deepcopy(definition.manifest)
    selected, profile, net0 = _profile(manifest, destino)
    if get_settings().infrastructure_profile.get('cluster_id') != manifest['validation']['cluster_uuid']:
        raise error(409, 'cluster_incompatible', 'La definición fue validada para otro clúster')
    transport = runner or GuestRunnerClient()
    if not callable(getattr(transport, 'execute', None)):
        raise error(409, 'runner_no_disponible', 'Falta el transporte cerrado del runner')
    if hasattr(transport, 'validar_destino'):
        try:
            transport.validar_destino(destino['nodo'])
        except RunnerError:
            raise error(409, 'runner_no_disponible', 'Configurá transporte y hostkey del runner institucional') from None
    await catalogo_service.comprobar_disponibilidad(manifest, pve=pve)
    return {'net0': net0, 'network_profile_id': selected, 'definition_sha256': asignacion['definition_sha256'],
        'bundle_sha256': manifest['preparation']['bundle_sha256']}


def _generate(product):
    if product == 'linux':
        return {'guest_password': secrets.token_urlsafe(32)}
    if product == 'postgresql':
        return {'database_password': secrets.token_urlsafe(32)}
    if product == 'bookstack':
        return {'teacher_password': secrets.token_urlsafe(32), 'database_password': secrets.token_urlsafe(32),
            'app_key': 'base64:' + base64.b64encode(secrets.token_bytes(32)).decode()}
    raise error(409, 'producto_no_soportado', 'La definición no tiene una preparación permitida')


async def preparar(*, sessions, servicio_id, operacion_id, identidad_id, lease, runner=None):
    from app.services import orquestacion_service as orchestration
    transport = runner or GuestRunnerClient()
    async with orchestration._locked(sessions, lease) as (db, op, identity, service, pedido, ledger):
        if (not service or not identity or service.id != servicio_id or op.id != operacion_id or identity.id != identidad_id
            or service.identidad_infraestructura_id != identity.id or op.fase != 'bootstrap'):
            raise orchestration.LeasePerdido()
        assignment = service.asignacion_snapshot or {}
        definition = await _definition(db, assignment)
        if (identity.definition_sha256 != definition.manifest_sha256
            or identity.bundle_sha256 != definition.manifest['preparation']['bundle_sha256']):
            raise error(409, 'identidad_sin_preparacion', 'La identidad histórica no acredita esta preparación')
        current = deepcopy(service.acceso_metadata or {})
        frozen = current.get('bootstrap_network_profile_id') or op.contexto_seguro.get('preparacion_validada', {}).get('network_profile_id')
        if not frozen:
            raise error(409, 'red_no_preparada', 'La operación no conserva el perfil validado antes de crear')
        selected, profile, _ = _profile(definition.manifest, op.contexto_seguro['destino'], frozen=frozen)
        parameters = current.get('bootstrap_parameters')
        if parameters is None:
            parameters = {'display_name': (assignment.get('nombre') or definition.codigo)[:100]}
            if definition.producto == 'bookstack':
                teacher = await db.get(Usuario, pedido.solicitante_id)
                if not teacher or not teacher.nombre or not teacher.email:
                    raise error(409, 'docente_incompleto', 'Completá nombre y correo del docente para su aplicación')
                parameters.update(teacher_name=teacher.nombre[:100], teacher_email=teacher.email, locale='es')
        if not service.credenciales_encrypted:
            if op.contexto_seguro.get('bootstrap_started') or current.get('bootstrap_parameters') is not None:
                raise InfraNoVerificable(incierto=True)
            values = _generate(definition.producto)
            service.credenciales_encrypted = configured_keyring().encrypt(values, context=f'servicio:{service.id}:secretos')
        else:
            values = configured_keyring().decrypt(service.credenciales_encrypted, context=f'servicio:{service.id}:secretos')
        nonce = configured_keyring().decrypt(identity.nonce_cifrado, context=f'infra:{identity.resource_uuid}:nonce')
        request = {'protocol': PROTOCOL, 'operation_id': str(op.id), 'action': 'bootstrap',
            'cluster_uuid': identity.cluster_id, 'resource_uuid': str(identity.resource_uuid), 'node': identity.nodo,
            'vmid': identity.vmid, 'pool': identity.pool_catedra, 'nonce': nonce,
            'definition_key': definition.codigo, 'definition_version': definition.version,
            'definition_sha256': identity.definition_sha256, 'bundle_sha256': identity.bundle_sha256,
            'network_profile_id': selected, 'parameters': parameters, 'secrets': values}
        current.update(bootstrap_parameters=parameters, bootstrap_network_profile_id=selected,
            preparacion_id=str(op.id), local_health=False, nonce_sha256=hashlib.sha256(nonce.encode()).hexdigest())
        service.acceso_metadata = current
        await orchestration._cas(db, lease, contexto_seguro={**op.contexto_seguro,
            'bootstrap_started': True, 'preparacion_id': str(op.id)})
        deadline = time.monotonic() + max(0, (db_utc(op.lease_until) - clock.now()).total_seconds())
        product = definition.producto
    # Commit de claves/fase antes de entregar stdin a un transporte. Las sesiones
    # no se comparten con el transporte ni permanecen bloqueadas durante SSH.
    if time.monotonic() >= deadline:
        raise orchestration.LeasePerdido()
    try:
        response = await transport.execute(request)
    except RunnerError:
        raise InfraNoVerificable(incierto=True) from None
    metadata = probes_servicio.confirmar(response, request, product=product, profile=profile,
        service_id=servicio_id, preparation_id=operacion_id)
    async with orchestration._locked(sessions, lease) as (db, op, identity, service, pedido, ledger):
        # La generación vencida no confirma ni reemplaza metadatos actuales.
        if service.id != servicio_id or op.id != operacion_id or identity.id != identidad_id:
            raise orchestration.LeasePerdido()
        metadata.update(bootstrap_parameters=parameters, bootstrap_network_profile_id=selected,
            nonce_sha256=hashlib.sha256(nonce.encode()).hexdigest())
    return {'identity_verified': True, 'local_health': True, 'acceso_metadata': metadata}
