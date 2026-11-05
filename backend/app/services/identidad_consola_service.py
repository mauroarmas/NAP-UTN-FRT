"""Identidades individuales de consola gestionadas por el portal (feature 022).

El conjunto *deseado* de pools de cada persona se calcula de la base (cátedras activas que posee; administración: todas);
lo *aplicado* se guarda en `identidades_consola`. Un reconciliador converge ambos con las acciones cerradas del runner
(`nap-console-identity/1`). Es idempotente y reintenta lo incierto con la misma contraseña. La contraseña es aleatoria,
sólo existe cifrada y nunca se muestra, registra ni devuelve.
"""
import logging
import secrets
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select

from app.config import get_settings
from app.models.catedra import Catedra
from app.models.identidad_consola import IdentidadConsola
from app.models.servicio import Servicio
from app.models.usuario import RolUsuario, Usuario
from app.schemas.guest_runner import RunnerError
from app.utils.clock import clock, db_utc
from app.utils.secretos import configured_keyring

log = logging.getLogger(__name__)
PROTOCOLO = 'nap-console-identity/1'
MENSAJE_ERROR = 'No se pudo confirmar en la infraestructura; se reintenta automáticamente.'
REINTENTO_SEGUNDOS = 30
LOTE_VMIDS = 200


def nombre_identidad(usuario_id):
    return f'nap-u{int(usuario_id)}@pve'


def _contexto(usuario_id):
    return f'identidad_consola:{usuario_id}'


def _cifrar(password, usuario_id):
    return configured_keyring().encrypt({'password': password}, context=_contexto(usuario_id))


def _descifrar(fila):
    return configured_keyring().decrypt(fila.password_cifrada, context=_contexto(fila.usuario_id))['password']


def _runner(runner):
    if runner is not None:
        return runner
    from app.services.guest_runner_client import GuestRunnerClient
    return GuestRunnerClient()


def _nodos():
    return sorted((get_settings().runner_nodes or {}).keys())


def _cluster():
    return str(get_settings().infrastructure_profile['cluster_id'])


# -- deseado ---------------------------------------------------------------------------------------------------------

async def deseados_por_usuario(db):
    """{usuario_id: [pool, …]} calculado de la base: persona activa → cátedras activas que posee (administración: todas)."""
    activas = {c.id: c.titular_id for c in (await db.scalars(select(Catedra).where(Catedra.activa.is_(True)))).all()}
    resultado = {}
    for usuario in (await db.scalars(select(Usuario))).all():
        if not usuario.activo:
            resultado[usuario.id] = []
        elif usuario.rol == RolUsuario.ADMIN:
            resultado[usuario.id] = sorted(f'catedra-{c}' for c in activas)
        else:
            resultado[usuario.id] = sorted(f'catedra-{c}' for c, titular in activas.items() if titular == usuario.id)
    return resultado


def _ids(pools):
    return [int(p.split('-', 1)[1]) for p in pools]


# -- runner ---------------------------------------------------------------------------------------------------------

async def _en_algun_nodo(runner, request):
    """ensure/retire/probe valen para todo el clúster: se prueba cada nodo hasta que uno responda."""
    ultimo = RunnerError('RUNNER_UNAVAILABLE')
    for nodo in _nodos():
        try:
            respuesta = await runner.execute_console_identity(request, nodo)
        except RunnerError as exc:
            ultimo = exc
            continue
        if respuesta['status'] == 'succeeded':
            return respuesta['result']
        codigo = (respuesta.get('error') or {}).get('code', 'UNCONFIRMED')
        ultimo = RunnerError(codigo)
        if codigo in {'INVALID_REQUEST', 'IDENTITY_MISMATCH', 'ROLE_UNAVAILABLE'}:
            break
    raise ultimo


def _pedido(accion, fila, **extra):
    return {'protocol': PROTOCOLO, 'operation_id': str(uuid4()), 'action': accion, 'cluster_uuid': _cluster(),
            'identidad': fila['identidad'], 'revision': fila['revision'], **extra}


async def terminar_sesiones(sessions, runner, pools):
    """Termina, en CADA nodo, las consolas abiertas de los contenedores de esos pools (la sesión vive en el nodo de entrada)."""
    if not pools:
        return 0
    async with sessions() as db:
        vmids = sorted({int(s.proxmox_vmid) for s in (await db.scalars(select(Servicio).where(
            Servicio.catedra_id.in_(_ids(pools)), Servicio.deleted_at.is_(None), Servicio.proxmox_vmid.is_not(None)))).all()
            if str(s.proxmox_vmid).isdigit()})
    total = 0
    for nodo in _nodos():
        for i in range(0, len(vmids), LOTE_VMIDS):
            pedido = {'protocol': PROTOCOLO, 'operation_id': str(uuid4()), 'action': 'end_sessions', 'cluster_uuid': _cluster(),
                      'identidad': 'nap-u0@pve', 'revision': 1, 'vmids': vmids[i:i + LOTE_VMIDS]}
            respuesta = await runner.execute_console_identity(pedido, nodo)
            if respuesta['status'] != 'succeeded':
                raise RunnerError((respuesta.get('error') or {}).get('code', 'UNCONFIRMED'))
            total += respuesta['result']['terminadas']
    return total


# -- reconciliación -------------------------------------------------------------------------------------------------

async def _datos(sessions, usuario_id):
    """Lee lo necesario en una transacción corta y devuelve un dict (sin objetos ORM vivos)."""
    async with sessions() as db, db.begin():
        usuario = await db.get(Usuario, usuario_id)
        if usuario is None:
            return None
        deseados = (await deseados_por_usuario(db)).get(usuario_id, [])
        fila = await db.scalar(select(IdentidadConsola).where(IdentidadConsola.usuario_id == usuario_id).with_for_update())
        if fila is None and not deseados:
            return None
        if fila is None:
            fila = IdentidadConsola(usuario_id=usuario_id, identidad=nombre_identidad(usuario_id),
                password_cifrada=_cifrar(secrets.token_urlsafe(32), usuario_id), estado='en_preparacion',
                pools_aplicados=[], revision=1)
            db.add(fila)
            await db.flush()
        elif fila.estado == 'retirada' and deseados:
            # La cuenta se eliminó al retirarla: vuelve con contraseña NUEVA (la anterior no puede reaparecer).
            fila.password_cifrada = _cifrar(secrets.token_urlsafe(32), usuario_id)
            fila.revision += 1
            fila.estado = 'en_preparacion'
        return {'identidad': fila.identidad, 'revision': fila.revision, 'estado': fila.estado, 'deseados': deseados,
                'aplicados': sorted(fila.pools_aplicados or [])}


async def _guardar(sessions, usuario_id, **cambios):
    async with sessions() as db, db.begin():
        fila = await db.scalar(select(IdentidadConsola).where(IdentidadConsola.usuario_id == usuario_id).with_for_update())
        for clave, valor in cambios.items():
            setattr(fila, clave, valor)
        fila.reconciliada_at = clock.now()


async def reconciliar_usuario(sessions, usuario_id, *, runner=None):
    """Converge la identidad de una persona con lo que debe tener. Devuelve el estado final o None si no hay nada que hacer."""
    runner = _runner(runner)
    datos = await _datos(sessions, usuario_id)
    if datos is None:
        return None
    deseados, aplicados = datos['deseados'], datos['aplicados']
    quitados = [p for p in aplicados if p not in deseados]
    try:
        if not deseados:
            if datos['estado'] == 'retirada':
                return 'retirada'
            await _en_algun_nodo(runner, _pedido('retire', datos))
            await terminar_sesiones(sessions, runner, quitados)
            if (await _en_algun_nodo(runner, _pedido('probe', datos)))['existe']:
                raise RunnerError('PROBE_FAILED')
            await _guardar(sessions, usuario_id, estado='retirada', pools_aplicados=[], ultimo_error_seguro=None)
            return 'retirada'
        async with sessions() as db:
            fila = await db.scalar(select(IdentidadConsola).where(IdentidadConsola.usuario_id == usuario_id))
            password = _descifrar(fila)
        resultado = await _en_algun_nodo(runner, _pedido('ensure', datos, password_consola=password, pools=deseados))
        await terminar_sesiones(sessions, runner, quitados)
        await _guardar(sessions, usuario_id, estado='lista', pools_aplicados=sorted(resultado['pools_aplicados']),
                       ultimo_error_seguro=None)
        return 'lista'
    except Exception as exc:   # sólo el CÓDIGO llega al registro; nunca texto del sistema ni la contraseña
        log.warning('identidad de consola: no se pudo reconciliar a la persona %s (%s)', usuario_id,
                    getattr(exc, 'code', type(exc).__name__))
        estado = 'lista' if datos['estado'] == 'lista' else 'con_error'
        await _guardar(sessions, usuario_id, estado=estado, ultimo_error_seguro=MENSAJE_ERROR)
        return estado


async def ciclo(sessions, *, runner=None):
    """Una pasada del reconciliador: lo que difiere entre lo deseado y lo aplicado, o lo que está en preparación/con error."""
    async with sessions() as db:
        deseados = await deseados_por_usuario(db)
        filas = {f.usuario_id: f for f in (await db.scalars(select(IdentidadConsola))).all()}
        ahora = clock.now()
        pendientes = []
        for usuario_id, pools in deseados.items():
            fila = filas.get(usuario_id)
            if fila is None:
                if pools:
                    pendientes.append(usuario_id)
                continue
            if fila.estado == 'retirada' and not pools:
                continue
            aplicados = set(fila.pools_aplicados or [])
            faltan, sobran = set(pools) - aplicados, aplicados - set(pools)
            reciente = fila.reconciliada_at is not None and (ahora - db_utc(fila.reconciliada_at)) < timedelta(seconds=REINTENTO_SEGUNDOS)
            # Un retiro (sobran) o una identidad con error/en preparación se atienden en la pasada; lo que falta sólo por un
            # pool que todavía no existe (faltan) se vuelve a mirar cada REINTENTO_SEGUNDOS para no pedirle al nodo en cada pasada.
            if sobran or fila.estado in {'en_preparacion', 'con_error'} or (faltan and not reciente):
                pendientes.append(usuario_id)
    resumen = {}
    for usuario_id in pendientes:
        resumen[usuario_id] = await reconciliar_usuario(sessions, usuario_id, runner=runner)
    return resumen


async def marcar_para_reintento(db, usuario_id):
    """Administración: reconciliar ya (la próxima pasada la toma sin esperar)."""
    fila = await db.scalar(select(IdentidadConsola).where(IdentidadConsola.usuario_id == usuario_id).with_for_update())
    if fila is None:
        return False
    fila.reconciliada_at = None
    if fila.estado == 'con_error':
        fila.estado = 'en_preparacion'
    return True
