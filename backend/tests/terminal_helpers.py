"""Dobles del navegador (WebSocket de FastAPI) y de la consola remota para probar la terminal web (feature 022)."""
import asyncio
import json


class Navegador:
    """Doble de `fastapi.WebSocket` del lado del portal: lo que la persona envía entra por `entradas`; lo recibido queda en `salidas`."""

    def __init__(self, cookies=None, headers=None):
        self.cookies, self.headers = cookies or {}, headers or {'origin': 'http://localhost:5173'}
        self.entradas, self.salidas, self.aceptado, self.codigo = asyncio.Queue(), [], False, None

    async def accept(self):
        self.aceptado = True

    async def receive(self):
        return await self.entradas.get()

    async def send_text(self, texto):
        self.salidas.append(('text', texto))

    async def send_bytes(self, datos):
        self.salidas.append(('bytes', datos))

    async def close(self, code=1000):
        self.codigo = code

    # utilidades de las pruebas
    def teclear(self, datos):
        self.entradas.put_nowait({'type': 'websocket.receive', 'bytes': datos})

    def controlar(self, **mensaje):
        self.entradas.put_nowait({'type': 'websocket.receive', 'text': json.dumps(mensaje)})

    def irse(self):
        self.entradas.put_nowait({'type': 'websocket.disconnect'})

    def mensajes(self):
        return [json.loads(v) for t, v in self.salidas if t == 'text']

    def salida_binaria(self):
        return b''.join(v for t, v in self.salidas if t == 'bytes')

    def cierre(self):
        return next((m for m in reversed(self.mensajes()) if m.get('t') == 'cierre'), None)


class Remoto:
    """Doble de `ConsolaRemota`."""

    def __init__(self):
        self.enviados, self.redimensionado, self.cerrado = [], None, False
        self.se_cierra_al_abrir = False      # simula la primera apertura cortada por la infraestructura
        self.hacia_el_portal = asyncio.Queue()

    async def vivo_tras(self, segundos):
        return not self.se_cierra_al_abrir

    async def enviar(self, datos):
        self.enviados.append(datos)

    async def redimensionar(self, columnas, filas):
        self.redimensionado = (columnas, filas)

    async def recibir(self):
        while True:
            datos = await self.hacia_el_portal.get()
            if datos is None:
                return
            yield datos

    async def cerrar(self):
        self.cerrado = True

    def emitir(self, datos):
        self.hacia_el_portal.put_nowait(datos)

    def cortar(self):
        self.hacia_el_portal.put_nowait(None)


def conector_secuencial(*remotos):
    """Cada llamada a `conectar` entrega el siguiente doble de consola remota."""
    llamadas, restantes = [], list(remotos)

    async def conectar(host, puerto, nodo, vmid, identidad, password):
        llamadas.append({'host': host, 'nodo': nodo, 'password': password})
        return restantes.pop(0)
    conectar.llamadas = llamadas
    return conectar


def conector(remoto, *, fallos=0, falla_hosts=()):
    """Devuelve una función `conectar(host, puerto, nodo, vmid, identidad, password)` que registra las llamadas."""
    from app.services.terminal_relay_service import RemotoNoDisponible
    llamadas = []

    async def conectar(host, puerto, nodo, vmid, identidad, password):
        llamadas.append({'host': host, 'puerto': puerto, 'nodo': nodo, 'vmid': vmid, 'identidad': identidad, 'password': password})
        if host in falla_hosts or len(llamadas) <= fallos:
            raise RemotoNoDisponible('prueba')
        return remoto
    conectar.llamadas = llamadas
    return conectar


async def esperar(condicion, *, segundos=10.0):
    """Espera activa y acotada a que se cumpla una condición."""
    fin = asyncio.get_event_loop().time() + segundos
    while asyncio.get_event_loop().time() < fin:
        if condicion():
            return True
        await asyncio.sleep(0.01)
    return False
