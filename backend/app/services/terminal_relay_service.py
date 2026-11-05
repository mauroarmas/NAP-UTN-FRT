"""Terminal web de la consola (feature 022): el portal abre la consola del contenedor con la identidad INDIVIDUAL de la
persona y la reenvía a una terminal del navegador. La persona nunca ve ni toca la infraestructura.

Seguridad: la contraseña de la identidad sólo está en memoria durante el inicio de sesión del relay; no se registra ni se
devuelve. Los bytes de la terminal pasan de largo: no se guardan, no se registran, no se auditan. Cada sesión está acotada
(tamaño de mensaje, cola de salida, inactividad, cupo por persona) y se corta de inmediato si se retira el acceso.
"""
import asyncio
import json
import logging
import ssl
import time
import urllib.parse
from types import SimpleNamespace

import httpx
import websockets
from sqlalchemy import select

from app.config import get_settings
from app.models.identidad_consola import IdentidadConsola
from app.models.servicio import EstadoServicio
from app.schemas.guest_runner import RunnerError
from app.services import terminal_sesiones_service as sesiones
from app.utils.clock import clock
from app.utils.errors import error

log = logging.getLogger(__name__)

CODIGOS_CIERRE = {'sin_permisos': 4403, 'servicio_no_disponible': 4409, 'consola_no_habilitada': 4409,
                  'identidad_no_confirmada': 4409, 'limite_sesiones': 4429, 'consola_nodo_no_disponible': 4503,
                  'sesion_invalida': 4401}
MENSAJES = {
    'inactividad': 'La terminal se cerró por inactividad. Podés abrir otra.',
    'persona': 'Terminal cerrada.',
    'retiro': 'Se retiró tu acceso a este servicio, por eso se cerró la terminal.',
    'baja': 'El servicio se dio de baja, por eso se cerró la terminal.',
    'detencion': 'El servicio se detuvo, por eso se cerró la terminal.',
    'cuenta': 'Tu sesión o tu cuenta ya no están vigentes. Ingresá de nuevo.',
    'administracion': 'Administración cerró esta terminal.',
    'error': 'Se perdió la conexión con el servicio. Podés abrir otra terminal.',
    'limite': 'Alcanzaste el máximo de terminales abiertas.',
}
AVISO_INACTIVIDAD_SEGUNDOS = 60
VIGILANCIA_SEGUNDOS = 2
LATIDO_SEGUNDOS = 5
REVALIDAR_SEGUNDOS = 10
ENVIO_NAVEGADOR_SEGUNDOS = 15
PRIMER_DATO_SEGUNDOS = 3.0


class RemotoNoDisponible(Exception):
    """No se pudo abrir la consola remota (conexión, saludo o ticket); sin detalles para la persona."""


# -- consola remota ---------------------------------------------------------------------------------------------------

def _tls():
    configuracion = get_settings()
    if configuracion.terminal_ca_file:
        contexto = ssl.create_default_context(cafile=configuracion.terminal_ca_file)
        return contexto, contexto
    if configuracion.proxmox_verify_ssl:
        contexto = ssl.create_default_context()
        return contexto, contexto
    # Sólo desarrollo (la configuración lo declara explícitamente): sin verificación.
    sin = ssl.create_default_context()
    sin.check_hostname, sin.verify_mode = False, ssl.CERT_NONE
    return False, sin


class ConsolaRemota:
    """Consola del contenedor abierta con el ticket de la identidad individual (protocolo de consola de la infraestructura)."""

    def __init__(self, ws):
        self.ws = ws
        self._previos = []

    async def vivo_tras(self, segundos):
        """False si la consola remota se cierra sin haber emitido nada (la primera apertura se corta a veces en la
        infraestructura); True si habló o sigue abierta. Lo leído se conserva y sale primero en `recibir`."""
        try:
            mensaje = await asyncio.wait_for(self.ws.recv(), segundos)
        except asyncio.TimeoutError:
            return True
        except (websockets.ConnectionClosed, OSError):
            return False
        self._previos.append(mensaje if isinstance(mensaje, bytes) else mensaje.encode())
        return True

    async def enviar(self, datos):
        await self.ws.send(b'0:' + str(len(datos)).encode() + b':' + datos)

    async def redimensionar(self, columnas, filas):
        await self.ws.send(f'1:{int(columnas)}:{int(filas)}:')

    async def recibir(self):
        while self._previos:
            yield self._previos.pop(0)
        async for mensaje in self.ws:
            yield mensaje if isinstance(mensaje, bytes) else mensaje.encode()

    async def cerrar(self):
        try:
            await self.ws.close()
        except Exception:
            pass


async def abrir_consola_remota(host, puerto, nodo_ct, vmid, identidad, password, *, timeout=10):
    """Ticket de sesión → pedido de consola del contenedor → WebSocket autenticado. La contraseña no sale de esta función."""
    verificar_http, contexto_ws = _tls()
    base = f'https://{host}:{puerto}/api2/json'
    try:
        async with httpx.AsyncClient(verify=verificar_http, timeout=timeout) as http:
            ticket = await http.post(base + '/access/ticket', data={'username': identidad, 'password': password})
            if ticket.status_code != 200:
                raise RemotoNoDisponible('ticket')
            datos = ticket.json()['data']
            cookie = 'PVEAuthCookie=' + urllib.parse.quote(datos['ticket'])
            termproxy = await http.post(f'{base}/nodes/{nodo_ct}/lxc/{int(vmid)}/termproxy', data={},
                headers={'Cookie': cookie, 'CSRFPreventionToken': datos['CSRFPreventionToken']})
            if termproxy.status_code != 200:
                raise RemotoNoDisponible('termproxy')
            consola = termproxy.json()['data']
        url = (f"wss://{host}:{puerto}/api2/json/nodes/{nodo_ct}/lxc/{int(vmid)}/vncwebsocket"
               f"?port={int(consola['port'])}&vncticket={urllib.parse.quote(consola['ticket'])}")
        ws = await websockets.connect(url, ssl=contexto_ws, additional_headers={'Cookie': cookie}, subprotocols=['binary'],
                                      open_timeout=timeout, max_size=2 ** 20)
        try:
            await ws.send(f"{consola['user']}:{consola['ticket']}\n")
            if await asyncio.wait_for(ws.recv(), timeout) != b'OK':
                raise RemotoNoDisponible('saludo')
        except BaseException:
            await ws.close()
            raise
        return ConsolaRemota(ws)
    except RemotoNoDisponible:
        raise
    except (httpx.HTTPError, OSError, asyncio.TimeoutError, websockets.WebSocketException, KeyError, ValueError, TypeError):
        raise RemotoNoDisponible('conexion') from None


def _candidatos(profile, nodo_ct):
    nodos = profile.get('nodos') or {}
    orden = [nodo_ct] + sorted(n for n in nodos if n != nodo_ct)
    # `portal_host` (opcional): la dirección con la que el PORTAL alcanza el nodo (y con la que su certificado se verifica);
    # `host` es la del navegador (sólo el respaldo de administración).
    return [(nodos[n].get('portal_host', nodos[n]['host']), nodos[n].get('port', 8006)) for n in orden if n in nodos]


async def conectar_con_reintento(profile, nodo_ct, vmid, identidad, password, *, conectar=abrir_consola_remota):
    """Prueba el nodo del contenedor y luego los demás; la primera apertura que se corta se reintenta una vez (FR-021)."""
    for host, puerto in _candidatos(profile, nodo_ct):
        for _ in range(2):
            try:
                return await conectar(host, puerto, nodo_ct, vmid, identidad, password)
            except RemotoNoDisponible:
                continue
    raise error(503, 'consola_nodo_no_disponible', 'La consola no está disponible ahora. Probá de nuevo en unos minutos.', reintentable=True)


# -- admisión ---------------------------------------------------------------------------------------------------------

async def autenticar_websocket(sessions, websocket):
    """Misma autenticación que las rutas HTTP (cookie de sesión del portal y propósito operativo) y `Origin` permitido."""
    from app.services import auth_service as auth
    from app.services.acceso_service import usuario_actual
    pedido = SimpleNamespace(cookies=websocket.cookies, headers=websocket.headers, state=SimpleNamespace(), method='GET')
    async with sessions() as db:
        usuario, sesion = await auth.autenticar(db, pedido, mutation_csrf=False)
        auth.exigir_proposito(sesion, 'operativo')
        usuario = await usuario_actual(db, usuario)
        return usuario.id


async def admitir(sessions, usuario_id, servicio_id):
    """Comprueba en el portal TODO antes de tocar la infraestructura y devuelve lo necesario para abrir la terminal."""
    from app.models.usuario import Usuario
    from app.services.acceso_service import requiere_acceso_servicio
    from app.services.consola_gate_service import autorizar
    from app.services.vigencia_service import periodos_vigentes, resumir_cobertura
    async with sessions() as db:
        usuario = await db.get(Usuario, usuario_id)
        servicio = await requiere_acceso_servicio(db, usuario, servicio_id)
        if servicio.estado != EstadoServicio.RUNNING:
            raise error(409, 'servicio_no_disponible', 'El servicio debe estar encendido para abrir la terminal.')
        if not resumir_cobertura(await periodos_vigentes(db, servicio.id), clock.now())['cubierto']:
            raise error(409, 'servicio_no_disponible', 'El servicio no tiene vigencia autorizada activa.')
        if not servicio.proxmox_vmid or not servicio.proxmox_node or not str(servicio.proxmox_vmid).isdigit():
            raise error(409, 'servicio_no_disponible', 'El servicio todavía no está listo para abrir la terminal.')
        perfil = await autorizar(db, servicio, usuario)
        fila = await db.scalar(select(IdentidadConsola).where(IdentidadConsola.usuario_id == usuario_id))
        from app.services.identidad_consola_service import _descifrar
        return {'servicio_id': servicio.id, 'nodo': servicio.proxmox_node, 'vmid': int(servicio.proxmox_vmid), 'perfil': perfil,
                'identidad': fila.identidad, 'password': _descifrar(fila)}


# -- servicio de una sesión -------------------------------------------------------------------------------------------

async def _aviso(navegador, texto):
    await navegador.send_text(json.dumps({'t': 'aviso', 'mensaje': texto}))


async def _cerrar_navegador(navegador, motivo, *, codigo=1000, mensaje=None):
    try:
        await navegador.send_text(json.dumps({'t': 'cierre', 'motivo': motivo, 'mensaje': mensaje or MENSAJES.get(motivo, MENSAJES['error'])}))
        await navegador.close(code=codigo)
    except Exception:
        pass


async def servir(navegador, sessions, servicio_id, *, conectar=abrir_consola_remota, reloj=time.monotonic):
    """Atiende una terminal de punta a punta. El `Origin` ya se validó antes de llamar (ver el router)."""
    configuracion = get_settings()
    # 1. Autenticación: sin sesión del portal no se acepta nada.
    try:
        usuario_id = await autenticar_websocket(sessions, navegador)
    except Exception as exc:
        await navegador.accept()
        await _cerrar_navegador(navegador, 'cuenta', codigo=CODIGOS_CIERRE['sesion_invalida'],
                                mensaje='Ingresá nuevamente para abrir la terminal.')
        return
    await navegador.accept()
    # 2. Admisión en el portal.
    try:
        admision = await admitir(sessions, usuario_id, servicio_id)
        sesion_id = await sesiones.abrir(sessions, usuario_id=usuario_id, servicio_id=servicio_id, nodo=admision['nodo'],
                                         limite=configuracion.terminal_max_sesiones)
    except Exception as exc:
        detalle = getattr(exc, 'detail', None)
        codigo = detalle.get('codigo') if isinstance(detalle, dict) else None
        if getattr(exc, 'status_code', None) in {403, 404}:
            # Sin acceso (o el servicio no existe): la misma respuesta, sin revelar cuál de las dos cosas pasa.
            codigo, detalle = 'sin_permisos', {'mensaje': 'No tenés acceso a este servicio.'}
        elif codigo is None:
            log.warning('terminal: admisión fallida (%s)', type(exc).__name__)
        await _cerrar_navegador(navegador, 'error', codigo=CODIGOS_CIERRE.get(codigo, 1011),
            mensaje=detalle.get('mensaje') if isinstance(detalle, dict) else 'No se pudo abrir la terminal ahora.')
        return
    motivo, remoto = 'error', None
    try:
        # 3. Consola remota con la identidad individual (la contraseña no se guarda en ninguna otra variable).
        try:
            password = admision.pop('password')
            argumentos = (admision['perfil'], admision['nodo'], admision['vmid'], admision['identidad'], password)
            remoto = await conectar_con_reintento(*argumentos, conectar=conectar)
            if not await remoto.vivo_tras(PRIMER_DATO_SEGUNDOS):
                # FR-021: la primera apertura que la infraestructura corta antes de emitir nada se reintenta UNA vez, sin avisar.
                await remoto.cerrar()
                remoto = await conectar_con_reintento(*argumentos, conectar=conectar)
            del password, argumentos
        except Exception as exc:
            detalle = getattr(exc, 'detail', None)
            await _cerrar_navegador(navegador, 'error', codigo=CODIGOS_CIERRE.get(detalle.get('codigo') if isinstance(detalle, dict) else None, 4503),
                mensaje=detalle.get('mensaje') if isinstance(detalle, dict) else MENSAJES['error'])
            return
        await navegador.send_text(json.dumps({'t': 'estado', 'e': 'abierta'}))
        motivo = await _retransmitir(navegador, remoto, sessions, sesion_id, usuario_id, reloj=reloj)
    except asyncio.CancelledError:
        motivo = 'reinicio_portal'
        raise
    finally:
        if remoto is not None:
            await remoto.cerrar()
        await sesiones.cerrar(sessions, sesion_id, motivo)
    await _cerrar_navegador(navegador, motivo, codigo=4408 if motivo == 'inactividad' else 4410 if motivo in {'retiro', 'baja', 'detencion', 'cuenta', 'administracion'} else 1000)


async def _retransmitir(navegador, remoto, sessions, sesion_id, usuario_id, *, reloj):
    configuracion = get_settings()
    limite_inactividad = configuracion.terminal_inactividad_segundos
    maximo = configuracion.terminal_max_mensaje_bytes
    estado = {'ultima_entrada': reloj(), 'ultima_entrada_dt': clock.now(), 'avisado': False}
    parar = asyncio.Event()      # el vigilante usa la base: se lo detiene con este evento, nunca cancelándolo a mitad de una consulta

    async def del_navegador():
        while True:
            mensaje = await navegador.receive()
            if mensaje['type'] == 'websocket.disconnect':
                return 'persona'
            datos = mensaje.get('bytes')
            if datos is not None:
                if len(datos) > maximo:
                    return 'error'
                estado['ultima_entrada'], estado['ultima_entrada_dt'], estado['avisado'] = reloj(), clock.now(), False
                await remoto.enviar(datos)
                continue
            try:
                control = json.loads(mensaje.get('text') or '')
                if control.get('t') == 'cerrar':
                    return 'persona'
                if control.get('t') == 'resize' and all(type(control.get(k)) is int and 1 <= control[k] <= 500 for k in ('cols', 'rows')):
                    await remoto.redimensionar(control['cols'], control['rows'])
            except (ValueError, AttributeError, TypeError):
                continue

    async def del_remoto():
        async for datos in remoto.recibir():
            await asyncio.wait_for(navegador.send_bytes(datos), ENVIO_NAVEGADOR_SEGUNDOS)
        return 'error'          # la consola remota se cerró: la cortó la infraestructura o un retiro

    async def vigilante():
        ultimo_latido = ultima_revalidacion = reloj()
        while True:
            try:
                await asyncio.wait_for(parar.wait(), VIGILANCIA_SEGUNDOS)
                return None
            except asyncio.TimeoutError:
                pass
            ahora = reloj()
            solicitado, motivo_pedido, cerrada = await sesiones.consultar(sessions, sesion_id)
            if cerrada:
                return 'error'
            if solicitado is not None:
                return motivo_pedido or 'retiro'
            inactivo = ahora - estado['ultima_entrada']
            if inactivo >= limite_inactividad:
                return 'inactividad'
            if inactivo >= limite_inactividad - AVISO_INACTIVIDAD_SEGUNDOS and not estado['avisado']:
                estado['avisado'] = True
                await _aviso(navegador, 'La terminal se cerrará en 1 minuto por inactividad. Escribí algo para mantenerla abierta.')
            if ahora - ultimo_latido >= LATIDO_SEGUNDOS:
                ultimo_latido = ahora
                await sesiones.latido(sessions, sesion_id, ultima_entrada=estado['ultima_entrada_dt'])
            if ahora - ultima_revalidacion >= REVALIDAR_SEGUNDOS:
                ultima_revalidacion = ahora
                try:
                    await autenticar_websocket(sessions, navegador)
                except Exception:
                    return 'cuenta'

    tareas = [asyncio.create_task(c()) for c in (del_navegador, del_remoto, vigilante)]
    vigilancia = tareas[2]
    try:
        hechas, _ = await asyncio.wait(tareas, return_when=asyncio.FIRST_COMPLETED)
        for tarea in hechas:
            if tarea.cancelled():
                continue
            if tarea.exception() is not None:
                log.warning('terminal: la sesión terminó por un fallo (%s)', type(tarea.exception()).__name__)
                return 'error'
            return tarea.result() or 'error'
        return 'error'
    finally:
        parar.set()
        for tarea in tareas[:2]:
            tarea.cancel()
        await asyncio.gather(*tareas[:2], return_exceptions=True)
        await asyncio.gather(vigilancia, return_exceptions=True)      # termina su consulta en curso y sale
