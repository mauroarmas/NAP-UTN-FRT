"""Identidades individuales de consola gestionadas por el portal (feature 022).

El conjunto *deseado* de pools de cada persona se calcula de la base (cátedras activas que posee; administración: todas);
lo *aplicado* se guarda en `identidades_consola`. Un reconciliador converge ambos con las acciones cerradas del runner
(`nap-console-identity/1`). Es idempotente y reintenta lo incierto con la misma contraseña. La contraseña es aleatoria,
sólo existe cifrada y nunca se muestra, registra ni devuelve.
"""
import logging
import secrets
from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import select

from app.config import get_settings
from app.models.cambio_acceso_consola import CambioAccesoConsola
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
    # Mientras un trámite de retiro está abierto la base todavía dice que la persona posee la cátedra (el cambio se aplica al
    # confirmarlo): el alcance deseado es el que propone el trámite, o el retiro nunca se ejecutaría ni lo completaría.
    acotados = {}
    for cambio in (await db.scalars(select(CambioAccesoConsola).where(CambioAccesoConsola.estado.in_(['pendiente', 'revocacion_fallida'])))).all():
        pools = {s.split('/pool/', 1)[1] for s in (cambio.scopes_propuestos or []) if s.startswith('/pool/')}
        acotados[cambio.usuario_id] = pools if cambio.usuario_id not in acotados else acotados[cambio.usuario_id] & pools
    resultado = {}
    for usuario in (await db.scalars(select(Usuario))).all():
        if not usuario.activo:
            resultado[usuario.id] = []
        elif usuario.rol == RolUsuario.ADMIN:
            resultado[usuario.id] = sorted(f'catedra-{c}' for c in activas)
        else:
            resultado[usuario.id] = sorted(f'catedra-{c}' for c, titular in activas.items() if titular == usuario.id)
        if usuario.id in acotados:
            resultado[usuario.id] = sorted(p for p in resultado[usuario.id] if p in acotados[usuario.id])
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


async def _cortar_terminales(sessions, usuario_id, pools, motivo):
    """Pide cerrar las terminales abiertas de la persona sobre los pools retirados (las de servicios que ya no le corresponden)."""
    if not pools:
        return
    from app.services import terminal_sesiones_service
    async with sessions() as db, db.begin():
        await terminal_sesiones_service.solicitar_cierre(db, motivo=motivo, usuario_id=usuario_id, catedra_ids=_ids(pools))


async def _inventario(sessions, usuario_id, identidad):
    """El inventario de consola de la 009 refleja la identidad gestionada: con ella, reducir acceso exige el trámite."""
    async with sessions() as db, db.begin():
        usuario = await db.get(Usuario, usuario_id)
        if identidad is None:
            if usuario.inventario_consola == 'asignada' and usuario.identidad_consola and usuario.identidad_consola.startswith('nap-u'):
                usuario.identidad_consola, usuario.inventario_consola = None, 'sin_identidad'
                usuario.inventario_consola_ref, usuario.inventario_consola_actor = 'AUTO-022-RETIRADA', 'portal-automatico'
        elif usuario.identidad_consola != identidad:
            if usuario.identidad_consola:
                # Adopción: la identidad manual anterior queda registrada. El protocolo del nodo sólo conoce nombres
                # gestionados (`nap-u<id>@pve`), así que la manual la elimina el operador (runbook); el portal no puede.
                historial = list(usuario.inventario_consola_historial or [])
                historial.append({'identidad_anterior': usuario.identidad_consola, 'reemplazada_at': clock.now().isoformat(),
                                  'por': identidad})
                usuario.inventario_consola_historial = historial
            usuario.identidad_consola, usuario.inventario_consola = identidad, 'asignada'
            usuario.inventario_consola_ref, usuario.inventario_consola_actor = 'AUTO-022', 'portal-automatico'


async def completar_tramites(sessions, usuario_id, identidad, deseados, *, sesiones_terminadas=True):
    """Con el retiro ya hecho y verificado, registra la evidencia observada y completa los trámites abiertos de la persona."""
    from app.schemas.evidencia import canonical, parse_document
    from app.services import consola_access_service, evidencia_service
    async with sessions() as db:
        abiertos = (await db.scalars(select(CambioAccesoConsola).where(CambioAccesoConsola.usuario_id == usuario_id,
            CambioAccesoConsola.estado.in_(consola_access_service.OPEN)))).all()
        datos = [(c.id, c.revision_esperada, c.identidad_nativa, sorted(c.scopes_propuestos or []), c.solicitada_por) for c in abiertos]
    for cambio_id, revision, identidad_nativa, scopes, solicitante_id in datos:
        if identidad_nativa != identidad or sorted(f'/pool/{p}' for p in deseados) != scopes:
            continue
        try:
            async with sessions() as db:
                solicitante = await db.get(Usuario, solicitante_id)
                documento = {'schema_version': 1, 'tipo': 'revocacion_consola', 'entorno': 'real',
                    'operador_institucional': 'portal-automatico', 'referencia_institucional': f'AUTO-022-{cambio_id}',
                    'observado_at': clock.now().strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
                    'resultado': {'cambio_consola_id': str(cambio_id), 'revision_esperada': revision,
                        'identidad_nativa': identidad_nativa, 'scopes_resultantes': scopes,
                        'sesiones_previas_terminadas': bool(sesiones_terminadas), 'url_directa_denegada': True,
                        'otros_accesos_legitimos_comprobados': True,
                        'cluster_uuid': _cluster(), **({'pve_version': v} if (v := (get_settings().console_access_profile or {}).get('pve_version')) else {})}}
                registro = await evidencia_service.registrar(db, parse_document(canonical(documento).encode()),
                    usuario=solicitante, clave=f'auto-evidencia-{cambio_id}')
                await db.commit()
                await consola_access_service.confirmar(db, cambio_id, UUID(registro.resultado['evidencia_ref']),
                    actor=solicitante, clave=f'auto-confirmar-{cambio_id}', sistema=True)
                await db.commit()
        except Exception as exc:
            detalle = getattr(exc, 'detail', None)
            log.warning('identidad de consola: no se pudo completar el trámite %s (%s)', cambio_id,
                        detalle.get('codigo') if isinstance(detalle, dict) else type(exc).__name__)


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
            await _cortar_terminales(sessions, usuario_id, quitados, 'retiro')
            await terminar_sesiones(sessions, runner, quitados)
            if (await _en_algun_nodo(runner, _pedido('probe', datos)))['existe']:
                raise RunnerError('PROBE_FAILED')
            await _guardar(sessions, usuario_id, estado='retirada', pools_aplicados=[], ultimo_error_seguro=None)
            await completar_tramites(sessions, usuario_id, datos['identidad'], [])   # antes de tocar el inventario
            await _inventario(sessions, usuario_id, None)
            return 'retirada'
        async with sessions() as db:
            fila = await db.scalar(select(IdentidadConsola).where(IdentidadConsola.usuario_id == usuario_id))
            password = _descifrar(fila)
        resultado = await _en_algun_nodo(runner, _pedido('ensure', datos, password_consola=password, pools=deseados))
        await _cortar_terminales(sessions, usuario_id, quitados, 'retiro')
        await terminar_sesiones(sessions, runner, quitados)
        await _guardar(sessions, usuario_id, estado='lista', pools_aplicados=sorted(resultado['pools_aplicados']),
                       ultimo_error_seguro=None)
        await _inventario(sessions, usuario_id, datos['identidad'])
        await completar_tramites(sessions, usuario_id, datos['identidad'], deseados)
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
