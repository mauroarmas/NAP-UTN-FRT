#!/usr/bin/env python3
"""Comprueba la terminal web DEL PORTAL (spec 022) hablando sólo con el portal, como lo haría un navegador.

Abre el WebSocket del portal con una sesión del portal y, dentro del contenedor, inicia sesión con un usuario y una
contraseña. No toca la infraestructura ni imprime contraseñas o cookies: sólo el resultado de cada comprobación.

  verificar-terminal-portal.py --url ws://<portal>/api/v1/servicios/<id>/terminal --origen <origen-permitido> \\
      --cookie-archivo <0600> --usuario nap --clave-archivo <0600> [--comando "id -un; sudo -n id -un"]
  verificar-terminal-portal.py ... --sin-cookie                 # debe cerrarse con 4401 (sin sesión)
  verificar-terminal-portal.py ... --origen https://ajeno.example   # el portal debe rechazar el origen

Requiere `pip install websockets`.
"""
import argparse
import asyncio
import json
import sys

import websockets


async def leer_hasta(ws, buf, marcas, espera):
    fin = asyncio.get_event_loop().time() + espera
    while asyncio.get_event_loop().time() < fin:
        for marca in marcas:
            if marca in buf[0]:
                antes, _, despues = buf[0].partition(marca)
                buf[0] = despues
                return marca, antes
        try:
            mensaje = await asyncio.wait_for(ws.recv(), 1.0)
        except asyncio.TimeoutError:
            continue
        if isinstance(mensaje, bytes):
            buf[0] += mensaje
        else:
            datos = json.loads(mensaje)
            if datos.get('t') == 'cierre':
                return 'CIERRE', datos
    return None, buf[0]


async def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--url', required=True)
    p.add_argument('--origen', required=True)
    p.add_argument('--cookie-archivo')
    p.add_argument('--sin-cookie', action='store_true')
    p.add_argument('--usuario', default='nap')
    p.add_argument('--clave-archivo')
    p.add_argument('--comando', default='')
    a = p.parse_args()
    cabeceras = {'Origin': a.origen}
    if not a.sin_cookie:
        cabeceras['Cookie'] = open(a.cookie_archivo).read().strip()
    try:
        ws = await websockets.connect(a.url, additional_headers=cabeceras, open_timeout=10)
    except websockets.exceptions.InvalidStatus as exc:
        print(f'rechazado antes de abrir (HTTP {exc.response.status_code})')
        return 0
    buf = [b'']
    primero = await asyncio.wait_for(ws.recv(), 15)
    estado = json.loads(primero) if isinstance(primero, str) else {}
    if estado.get('t') == 'cierre':
        print(f"cierre inmediato: codigo {ws.close_code or 'n/d'}; mensaje: {estado.get('mensaje')}")
        return 0
    if estado != {'t': 'estado', 'e': 'abierta'}:
        print('respuesta inesperada del portal'); return 1
    print('terminal abierta (el navegador no recibió ninguna dirección de la infraestructura)')
    clave = open(a.clave_archivo).read().strip()
    await ws.send(json.dumps({'t': 'resize', 'cols': 120, 'rows': 30}))
    # La consola de la infraestructura es persistente: si una sesión anterior quedó iniciada, primero se la cierra.
    for _ in range(3):
        await ws.send(b'\x03\n')
        marca, _ = await leer_hasta(ws, buf, [b'login: ', b'$ ', b'# '], 10)
        if marca == b'login: ':
            break
        if marca in (b'$ ', b'# '):
            await ws.send(b'exit\n')
            marca, _ = await leer_hasta(ws, buf, [b'login: '], 10)
            if marca == b'login: ':
                break
    if marca != b'login: ':
        print('no apareció el prompt de login'); return 1
    await ws.send(a.usuario.encode() + b'\n')
    await leer_hasta(ws, buf, [b'assword:'], 8)
    await ws.send(clave.encode() + b'\n')
    marca, _ = await leer_hasta(ws, buf, [b'Login incorrect', b'$ ', b'# '], 12)
    if marca in (None, b'Login incorrect'):
        print(f'{a.usuario}: rechazado'); return 0
    resultado = f'{a.usuario}: entra'
    if a.comando:
        await ws.send(a.comando.encode() + b'\n')
        _, salida = await leer_hasta(ws, buf, [b'$ ', b'# '], 10)
        salida = salida if isinstance(salida, bytes) else b''
        lineas = [l.strip() for l in salida.decode(errors='replace').replace('\r', '').split('\n')[1:] if l.strip()]
        resultado += ' [' + ' | '.join(lineas)[:140] + ']'
    await ws.send(b'exit\n')
    await leer_hasta(ws, buf, [b'login: '], 10)      # esperar a que se procese: la consola persiste entre conexiones
    await ws.send(json.dumps({'t': 'cerrar'}))
    print(resultado)
    await ws.close()
    return 0


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
