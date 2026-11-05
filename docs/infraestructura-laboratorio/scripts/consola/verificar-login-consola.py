#!/usr/bin/env python3
"""Comprueba el inicio de sesión REAL dentro de la consola de un contenedor Linux (spec 021).

Abre la consola por el protocolo de Proxmox con una identidad de consola de prueba y, dentro del contenedor, intenta
iniciar sesión con un usuario y una contraseña. No imprime contraseñas ni tickets: sólo el resultado de cada comprobación.

  verificar-login-consola.py --entrada <ip-nodo> --nodo <nodo-del-ct> --vmid <id> --usuario-pve <u>@<dominio> \\
      --clave-pve-archivo <0600> --intentos nap:<archivo-clave> root:<archivo-clave> [--comando "id -un; sudo -n id -un"]

Cada intento `<usuario>:<archivo>` devuelve `entra` (obtiene una shell y, si se pasó --comando, lo ejecuta) o `rechazado`.
Requiere `pip install websockets`. Los archivos de clave deben ser privados (0600).
"""
import argparse
import asyncio
import json
import ssl
import sys
import urllib.parse
import urllib.request

import websockets

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def api(host, ruta, metodo='GET', datos=None, cab=None):
    req = urllib.request.Request(f'https://{host}:8006/api2/json{ruta}', method=metodo, headers=cab or {},
        data=urllib.parse.urlencode(datos).encode() if datos is not None else None)
    with urllib.request.urlopen(req, context=CTX, timeout=20) as r:
        return json.load(r)['data']


class Terminal:
    def __init__(self, ws):
        self.ws, self.buf = ws, b''

    async def enviar(self, texto):
        datos = texto.encode()
        await self.ws.send(b'0:' + str(len(datos)).encode() + b':' + datos)

    async def leer_hasta(self, marcas, espera=8.0):
        """Lee hasta ver alguna de `marcas` (bytes); devuelve (marca|None, texto leído)."""
        fin = asyncio.get_event_loop().time() + espera
        while asyncio.get_event_loop().time() < fin:
            for marca in marcas:
                if marca in self.buf:
                    antes, _, despues = self.buf.partition(marca)
                    self.buf = despues
                    return marca, antes
            try:
                self.buf += await asyncio.wait_for(self.ws.recv(), 1.0)
            except asyncio.TimeoutError:
                continue
        return None, self.buf


async def abrir(args, clave_pve):
    t = api(args.entrada, '/access/ticket', 'POST', {'username': args.usuario_pve, 'password': clave_pve})
    cab = {'Cookie': 'PVEAuthCookie=' + urllib.parse.quote(t['ticket']), 'CSRFPreventionToken': t['CSRFPreventionToken']}
    tp = api(args.entrada, f'/nodes/{args.nodo}/lxc/{args.vmid}/termproxy', 'POST', {}, cab)
    url = (f'wss://{args.entrada}:8006/api2/json/nodes/{args.nodo}/lxc/{args.vmid}/vncwebsocket'
           f"?port={tp['port']}&vncticket={urllib.parse.quote(tp['ticket'])}")
    ws = await websockets.connect(url, ssl=CTX, additional_headers={'Cookie': cab['Cookie']}, subprotocols=['binary'], open_timeout=10)
    await ws.send(f"{tp['user']}:{tp['ticket']}\n")
    if await asyncio.wait_for(ws.recv(), 8) != b'OK':
        raise SystemExit('consola rechazada')
    await ws.send('1:120:30:')
    return Terminal(ws)


async def intentar(term, usuario, clave, comando):
    # Llegar a un prompt de login limpio aunque una sesión anterior haya quedado a medias (Ctrl-C cancela el login pendiente).
    term.buf = b''
    await term.enviar('\x03\n')
    marca, _ = await term.leer_hasta([b'login: '], 12)
    if marca is None:
        await term.enviar('\n')
        marca, _ = await term.leer_hasta([b'login: '], 12)
    if marca is None:
        return 'sin_prompt'
    await term.enviar(usuario + '\n')
    marca, _ = await term.leer_hasta([b'Password: ', b'assword:'], 8)
    if marca is None:
        return 'sin_prompt_clave'
    await term.enviar(clave + '\n')
    marca, _ = await term.leer_hasta([b'Login incorrect', b'$ ', b'# '], 10)
    if marca == b'Login incorrect' or marca is None:
        await term.leer_hasta([b'login: '], 6)
        return 'rechazado'
    resultado = 'entra'
    if comando:
        await term.enviar(comando + '\n')
        _, salida = await term.leer_hasta([b'$ ', b'# '], 8)
        resultado += ' [' + ' | '.join(l.strip() for l in salida.decode(errors='replace').replace('\r', '').split('\n')[1:] if l.strip())[:120] + ']'
    await term.enviar('exit\n')
    await term.leer_hasta([b'login: '], 8)
    return resultado


async def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--entrada', required=True); p.add_argument('--nodo', required=True); p.add_argument('--vmid', type=int, required=True)
    p.add_argument('--usuario-pve', required=True); p.add_argument('--clave-pve-archivo', required=True)
    p.add_argument('--intentos', nargs='+', required=True, help='<usuario>:<archivo con la contraseña>')
    p.add_argument('--comando', default='')
    a = p.parse_args()
    term = await abrir(a, open(a.clave_pve_archivo).read().strip())
    fallos = 0
    for item in a.intentos:
        usuario, archivo = item.split(':', 1)
        resultado = await intentar(term, usuario, open(archivo).read().strip(), a.comando)
        print(f'{usuario}: {resultado}')
    await term.ws.close()
    return 0


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
