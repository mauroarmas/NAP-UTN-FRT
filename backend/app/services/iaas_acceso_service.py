"""Acceso SSH con clave pública a servicios Linux IaaS (feature 017).

Nada de lo que pasa por acá toca Proxmox directamente: el efecto en el contenedor lo ejecuta el
runner del nodo (`nap-iaas-access/1`) y el reemplazo de clave es una operación durable.
Solo se guarda material público; en historial y respuestas solo aparece la huella.
"""
import hashlib

from sqlalchemy import select

from app.models.clave_acceso_servicio import ClaveAccesoServicio
from app.models.compromiso_capacidad import CompromisoCapacidad
from app.models.identidad_infraestructura import IdentidadInfraestructura
from app.models.operacion_infraestructura import OperacionInfraestructura
from app.models.servicio import Servicio, EstadoServicio
from app.schemas.guest_runner import RunnerError
from app.utils.clock import clock
from app.utils.errors import error
from app.utils.secretos import configured_keyring
from app.utils.ssh_keys import ClaveSshInvalida, validar_clave

USUARIO = 'nap'
# Errores del nodo que no se arreglan reintentando: el servicio queda con el motivo, no en espera.
DEFINITIVOS = {'IDENTITY_MISMATCH', 'SSHD_UNAVAILABLE', 'SUDO_UNAVAILABLE', 'INVALID_REQUEST'}
MOTIVOS = {
    'SSHD_UNAVAILABLE': 'La plantilla Linux no trae el servicio de acceso remoto (SSH).',
    'SUDO_UNAVAILABLE': 'La plantilla Linux no trae sudo.',
    'IDENTITY_MISMATCH': 'El contenedor no coincide con el servicio registrado.',
    'INVALID_REQUEST': 'La solicitud de acceso no es válida.',
}


class AccesoSshRechazado(Exception):
    """El nodo rechazó definitivamente la configuración; el orquestador cierra la operación con este código."""
    def __init__(self, codigo):
        self.codigo = 'acceso_ssh_' + codigo.lower()
        super().__init__(self.codigo)


def normalizar(texto):
    """(tipo, clave_normalizada, huella) o un 422 con código estable y mensaje para la persona."""
    try:
        return validar_clave(texto)
    except ClaveSshInvalida as exc:
        raise error(422, exc.codigo, exc.mensaje) from None


def es_servicio_linux(servicio):
    return bool(servicio and servicio.modelo_servicio == 'iaas'
        and (servicio.asignacion_snapshot or {}).get('origen') == 'proxmox_iaas')


def validar_solicitud(template, data):
    """En el pedido: una base Linux del catálogo exige clave; cualquier otro servicio la rechaza."""
    from app.services.bases_iaas_service import es_base
    clave = data.parametros_extra.clave_ssh_publica if data.parametros_extra else None
    if es_base(template):
        if not clave or not clave.strip():
            raise error(422, 'clave_ssh_requerida', 'Pegá tu clave pública SSH para poder entrar al servicio.')
        normalizar(clave)
    elif clave:
        raise error(422, 'clave_ssh_no_aplica', 'Este servicio no usa clave SSH.')


def parametros_normalizados(parametros):
    """Copia de parametros_extra con la clave ya normalizada (sin comentario)."""
    parametros = dict(parametros or {})
    if parametros.get('clave_ssh_publica'):
        parametros['clave_ssh_publica'] = normalizar(parametros['clave_ssh_publica'])[1]
    return parametros


def bloque_asignacion(pedido):
    """Datos públicos de la clave para la asignación congelada del pedido aprobado."""
    clave = (pedido.parametros_extra or {}).get('clave_ssh_publica')
    if not clave:
        raise error(409, 'clave_ssh_requerida', 'El pedido de Linux no tiene clave pública SSH registrada')
    tipo, normalizada, huella = normalizar(clave)
    return {'tipo': tipo, 'clave_publica': normalizada, 'huella': huella, 'usuario': USUARIO}


def crear_fila(db, servicio, asignacion, solicitante_id):
    """Al materializar el servicio: una fila por servicio, revisión 1, todavía sin aplicar."""
    bloque = (asignacion or {}).get('acceso_ssh')
    if not bloque:
        return None
    fila = ClaveAccesoServicio(servicio_id=servicio.id, tipo=bloque['tipo'], clave_publica=bloque['clave_publica'],
        huella_sha256=bloque['huella'], usuario=USUARIO, revision=1, registrada_por_id=solicitante_id, registrada_at=clock.now())
    db.add(fila)
    return fila


async def fila_de(db, servicio_id):
    return await db.scalar(select(ClaveAccesoServicio).where(ClaveAccesoServicio.servicio_id == servicio_id))


def _solicitud(identity, fila, *, operacion_id, accion, nonce):
    base = {'protocol': 'nap-iaas-access/1', 'operation_id': str(operacion_id), 'action': accion,
        'cluster_uuid': str(identity.cluster_id), 'resource_uuid': str(identity.resource_uuid), 'node': identity.nodo,
        'vmid': identity.vmid, 'pool': identity.pool_catedra, 'nonce': nonce, 'revision': fila['revision'], 'usuario': USUARIO}
    if accion == 'configure':
        return {**base, 'clave_publica': fila['clave_publica']}
    return {**base, 'huella': fila['huella']}


async def aplicar(sessions, *, runner, identity, servicio_id, operacion_id):
    """Configura el acceso en el contenedor. Devuelve el bloque `ssh` para acceso_metadata, o None si no hay clave.

    Idempotente por revisión: repetirlo converge al mismo estado, así que un resultado incierto se reintenta igual.
    """
    from app.services.infraestructura_io import InfraNoVerificable
    async with sessions() as db:
        fila = await fila_de(db, servicio_id)
        if fila is None:
            return None
        datos = {'revision': fila.revision, 'clave_publica': fila.clave_publica, 'huella': fila.huella_sha256}
    nonce = configured_keyring().decrypt(identity.nonce_cifrado, context=f'infra:{identity.resource_uuid}:nonce')
    if runner is None:
        from app.services.guest_runner_client import GuestRunnerClient
        runner = GuestRunnerClient()
    try:
        respuesta = await runner.execute_iaas_access(_solicitud(identity, datos, operacion_id=operacion_id, accion='configure', nonce=nonce))
    except RunnerError:
        raise InfraNoVerificable(incierto=True) from None
    if respuesta['status'] != 'succeeded':
        codigo = (respuesta.get('error') or {}).get('code', 'UNCONFIRMED')
        if respuesta['status'] == 'failed' and codigo in DEFINITIVOS:
            raise AccesoSshRechazado(codigo)
        raise InfraNoVerificable(incierto=True)
    resultado = respuesta['result']
    if resultado.get('revision') != datos['revision'] or resultado.get('huella') != datos['huella']:
        raise InfraNoVerificable(incierto=True)
    ahora = clock.now()
    async with sessions() as db, db.begin():
        fila = await db.scalar(select(ClaveAccesoServicio).where(ClaveAccesoServicio.servicio_id == servicio_id).with_for_update())
        if fila is not None and fila.revision == datos['revision']:
            fila.aplicada_revision, fila.aplicada_at = datos['revision'], ahora
    return {'usuario': USUARIO, 'puerto': 22, 'huella': datos['huella'], 'revision': datos['revision'],
        'verificado_at': ahora.isoformat(), **({'direccion': resultado['direccion']} if resultado.get('direccion') else {})}


async def refrescar_direccion(sessions, *, runner, identity, servicio_id, operacion_id):
    """Al iniciar el servicio: vuelve a leer la IP que el contenedor tiene de verdad. Nunca hace fallar la orden.

    El DHCP puede entregar una dirección distinta de la reservada o cambiarla; el comando de conexión tiene que
    usar la que el contenedor realmente tiene. Si el nodo no responde, se conserva la última conocida.
    """
    try:
        async with sessions() as db:
            fila = await fila_de(db, servicio_id)
            if fila is None or fila.aplicada_revision != fila.revision:
                return None
            datos = {'revision': fila.revision, 'huella': fila.huella_sha256}
        nonce = configured_keyring().decrypt(identity.nonce_cifrado, context=f'infra:{identity.resource_uuid}:nonce')
        if runner is None:
            from app.services.guest_runner_client import GuestRunnerClient
            runner = GuestRunnerClient()
        respuesta = await runner.execute_iaas_access(_solicitud(identity, datos, operacion_id=operacion_id, accion='probe', nonce=nonce))
        direccion = (respuesta.get('result') or {}).get('direccion') if respuesta.get('status') == 'succeeded' else None
        if not direccion:
            return None
        async with sessions() as db, db.begin():
            servicio = await db.get(Servicio, servicio_id, with_for_update=True)
            if servicio is None:
                return None
            ssh = dict((servicio.acceso_metadata or {}).get('ssh') or {})
            if ssh.get('direccion') == direccion:
                return direccion
            ssh.update(direccion=direccion, verificado_at=clock.now().isoformat())
            servicio.acceso_metadata = {**(servicio.acceso_metadata or {}), 'ssh': ssh}
        return direccion
    except Exception:  # Es una mejora de presentación: un fallo no puede impedir iniciar el servicio.
        return None


def estado_derivado(fila, *, operacion_abierta):
    if fila is None:
        return 'sin_clave'
    if fila.aplicada_revision == fila.revision:
        return 'aplicada'
    return 'pendiente' if operacion_abierta else 'fallida'


async def bloque_acceso(db, servicio, *, cubierto):
    """Bloque `acceso_ssh` del detalle de acceso; el comando solo aparece si realmente se puede usar."""
    from app.services.operacion_service import OPEN
    fila = await fila_de(db, servicio.id)
    abierta = bool(await db.scalar(select(OperacionInfraestructura.id).where(
        OperacionInfraestructura.servicio_id == servicio.id, OperacionInfraestructura.estado.in_(OPEN)).limit(1)))
    estado = estado_derivado(fila, operacion_abierta=abierta)
    metadata = servicio.acceso_metadata or {}
    direcciones = metadata.get('addresses') or []
    # Preferimos la IP que el contenedor tiene de verdad (la reservada puede no coincidir si el DHCP no la respeta).
    direccion = (metadata.get('ssh') or {}).get('direccion') or (direcciones[0] if direcciones else None)
    en_marcha = servicio.estado == EstadoServicio.RUNNING
    puede = bool(estado == 'aplicada' and en_marcha and cubierto and direccion)
    motivo = None
    if estado == 'sin_clave':
        motivo = 'Este servicio todavía no tiene una clave SSH registrada. Agregá tu clave pública para poder entrar.'
    elif estado == 'pendiente':
        motivo = 'Estamos configurando el acceso. Se habilita cuando termina la comprobación.'
    elif estado == 'fallida':
        motivo = 'No se pudo configurar el acceso SSH. Probá cargar la clave de nuevo o avisá a administración.'
    elif not en_marcha or not cubierto:
        motivo = 'Iniciá el servicio con vigencia autorizada antes de conectarte.'
    elif not direccion:
        motivo = 'El servicio todavía no tiene dirección asignada.'
    return {'estado': estado, 'usuario': USUARIO, 'direccion': direccion if puede else None, 'puerto': 22,
        'comando': f'ssh {USUARIO}@{direccion}' if puede else None,
        'huella': fila.huella_sha256 if fila else None,
        'verificado_at': fila.aplicada_at.isoformat() if fila and fila.aplicada_at else None,
        'puede_conectar': puede, 'motivo': motivo}


async def registrar_o_reemplazar(db, *, actor, servicio_id, clave, idempotency_key):
    """Alta tardía o reemplazo: sube la revisión y encola una operación `reparar` que reaplica la clave."""
    from app.services import capacidad_service
    from app.services.acceso_service import requiere_acceso_catedra, requiere_acceso_servicio, usuario_actual
    from app.services.admision_service import operation_response
    from app.services.historial_service import registrar_servicio
    from app.services.idempotencia_service import ejecutar, ResultadoDecision, safe_json
    from app.services.operacion_service import OPEN
    actor = await usuario_actual(db, actor)
    await requiere_acceso_servicio(db, actor, servicio_id)
    tipo, normalizada, huella = normalizar(clave)

    async def decide(session):
        async with capacidad_service.bloqueo_capacidad(session):
            service = await session.scalar(select(Servicio).where(Servicio.id == servicio_id).with_for_update()
                .execution_options(populate_existing=True))
            if service is None or service.deleted_at:
                raise error(409, 'servicio_no_activo', 'El servicio ya fue dado de baja')
            await requiere_acceso_catedra(session, actor, service.catedra_id)
            if not es_servicio_linux(service):
                raise error(409, 'servicio_no_linux', 'Solo los servicios Linux se conectan por SSH')
            previous = await session.scalar(select(OperacionInfraestructura).where(
                OperacionInfraestructura.servicio_id == service.id, OperacionInfraestructura.estado.in_(OPEN)).with_for_update())
            if previous:
                raise error(409, 'operacion_en_curso', 'Ya existe una operación abierta', operation_id=str(previous.id))
            if service.estado != EstadoServicio.RUNNING:
                raise error(409, 'servicio_detenido', 'Iniciá el servicio para poder cambiar la clave de acceso')
            identity = await session.get(IdentidadInfraestructura, service.identidad_infraestructura_id) if service.identidad_infraestructura_id else None
            ledger = await session.scalar(select(CompromisoCapacidad).where(CompromisoCapacidad.servicio_id == service.id,
                CompromisoCapacidad.liberado_at.is_(None)).with_for_update())
            if not identity or identity.ausencia_confirmada_at or not ledger or not service.asignacion_snapshot:
                raise error(409, 'asignacion_sin_regularizar', 'Regularizá identidad y asignación antes de operar')
            fila = await fila_de(session, service.id)
            if fila is None:
                fila = ClaveAccesoServicio(servicio_id=service.id, tipo=tipo, clave_publica=normalizada, huella_sha256=huella,
                    usuario=USUARIO, revision=1, registrada_por_id=actor.id, registrada_at=clock.now())
                session.add(fila)
                accion = 'registrada'
            elif fila.huella_sha256 == huella and fila.aplicada_revision == fila.revision:
                return ResultadoDecision(200, {'servicio_id': service.id, 'huella': huella, 'revision': fila.revision,
                    'estado': 'aplicada', 'sin_cambios': True})
            else:
                fila.tipo, fila.clave_publica, fila.huella_sha256 = tipo, normalizada, huella
                fila.revision, fila.registrada_por_id, fila.registrada_at = fila.revision + 1, actor.id, clock.now()
                accion = 'reemplazada'
            operation = OperacionInfraestructura(tipo='reparar', servicio_id=service.id, pedido_id=service.pedido_id,
                identidad_infraestructura_id=identity.id, actor_usuario_id=actor.id, actor_tipo='usuario',
                actor_id_normalizado=str(actor.id), idempotency_key=idempotency_key,
                request_hash=hashlib.sha256(safe_json({'acceso_ssh': huella}).encode()).hexdigest(),
                motivo='Acceso SSH: clave ' + accion, estado='pendiente', fase='preparacion', creado_at=clock.now(),
                updated_at=clock.now(), next_poll_at=clock.now(),
                contexto_seguro={'catedra_id': service.catedra_id, 'asignacion': service.asignacion_snapshot,
                    'destino': {'nodo': ledger.nodo, 'storage': ledger.storage_id, 'storage_scope': ledger.storage_scope},
                    'acceso_ssh': {'revision': fila.revision}})
            session.add(operation)
            await session.flush()
            session.add(registrar_servicio(service.id, service.estado.value, service.estado.value,
                comentario=f'Clave de acceso SSH {accion} ({huella}); resultado pendiente', usuario=actor,
                operacion_id=operation.id, evento_clave=f'operacion:{operation.id}:acceso_ssh'))
            respuesta = operation_response(operation)
            respuesta.update(huella=huella, revision=fila.revision, estado='pendiente')
            return ResultadoDecision(202, respuesta)

    return await ejecutar(db, actor_id=actor.id, actor_tipo='usuario', clave=idempotency_key, metodo='PUT',
        ruta=f'/servicios/{servicio_id}/acceso-ssh', payload={'clave_publica': normalizada}, decidir=decide,
        target_tipo='servicio', target_id=servicio_id)
