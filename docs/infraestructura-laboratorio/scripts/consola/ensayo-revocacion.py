#!/usr/bin/env python3
"""Ensayo real de revocación de la consola nativa (spec 020, FR-007).

Abre consolas REALES de una identidad individual, retira el acceso por el procedimiento institucional
(`retirar-acceso.sh`) y registra, por separado, lo que se observó:

  1. la sesión abierta del pool retirado deja de transmitir (y cuánto tardó)
  2. un ticket/solicitud guardado antes del retiro es rechazado
  3. con otro pool vigente, una sesión nueva sigue abriendo
  4. eliminar la identidad invalida sus tickets de sesión y se terminan sus consolas restantes

Requisitos: Python 3.10+, `pip install websockets`, ssh con clave a cada nodo como root, y los scripts de este
directorio copiados en cada nodo. Los hosts, usuarios y contraseñas se pasan por argumentos o archivos privados;
el informe no contiene tickets ni cookies. Si algún punto falla, la consola debe permanecer deshabilitada (FR-008).

Ejemplo (marcadores):
  ensayo-revocacion.py --nodos <ip-nodo-1> <ip-nodo-2> --usuario <usuario>@pve --clave-archivo <archivo-0600> \\
      --ct <nodo>:<vmid>:catedra-<N> --otro-ct <nodo>:<vmid>:catedra-<M> --informe <salida.json>
"""
import argparse
import asyncio
import json
import os
import ssl
import subprocess
import sys
import time
from datetime import datetime, timezone
import urllib.error
import urllib.parse
import urllib.request

import websockets

SCRIPTS_REMOTOS = os.environ.get('NAP_SCRIPTS_REMOTOS', '/root/nap-consola')
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE   # los nodos usan certificado propio; el ensayo no valida TLS, la instalación sí debe


def api(host, ruta, metodo='GET', datos=None, cabeceras=None, puerto=8006):
    req = urllib.request.Request(
        f'https://{host}:{puerto}/api2/json{ruta}', method=metodo, headers=cabeceras or {},
        data=urllib.parse.urlencode(datos).encode() if datos is not None else None)
    try:
        with urllib.request.urlopen(req, context=CTX, timeout=20) as resp:
            return resp.status, json.load(resp).get('data')
    except urllib.error.HTTPError as exc:
        return exc.code, None


def ssh(nodo, orden, entrada=None):
    ctl = os.environ.get('NAP_SSH_CTL', '/tmp/nap-lab-ssh-%h')
    out = subprocess.run(['ssh', '-o', f'ControlPath={ctl}', '-o', 'BatchMode=yes', f'root@{nodo}', 'LC_ALL=C ' + orden],
                         input=entrada, capture_output=True, text=True, timeout=120)
    return out.returncode, out.stdout


def login(host, usuario, clave):
    estado, datos = api(host, '/access/ticket', 'POST', {'username': usuario, 'password': clave})
    if estado != 200:
        return None
    return {'Cookie': 'PVEAuthCookie=' + urllib.parse.quote(datos['ticket']),
            'CSRFPreventionToken': datos['CSRFPreventionToken']}


class Sesion:
    """Una consola real abierta por la API de un nodo cualquiera del clúster."""

    def __init__(self, host, nodo_ct, vmid, cab, ticket):
        self.host, self.nodo, self.vmid, self.cab, self.ticket = host, nodo_ct, vmid, cab, ticket
        self.ws = None

    @staticmethod
    def solicitar(host, nodo_ct, vmid, cab):
        estado, datos = api(host, f'/nodes/{nodo_ct}/lxc/{vmid}/termproxy', 'POST', {}, cab)
        return estado, datos

    def url(self):
        return (f'wss://{self.host}:8006/api2/json/nodes/{self.nodo}/lxc/{self.vmid}/vncwebsocket'
                f"?port={self.ticket['port']}&vncticket={urllib.parse.quote(self.ticket['ticket'])}")

    async def abrir(self):
        self.ws = await websockets.connect(self.url(), ssl=CTX, additional_headers={'Cookie': self.cab['Cookie']},
                                           subprotocols=['binary'], open_timeout=10)
        await self.ws.send(f"{self.ticket['user']}:{self.ticket['ticket']}\n")
        if await asyncio.wait_for(self.ws.recv(), 8) != b'OK':
            raise RuntimeError('saludo de consola rechazado')
        await self.ws.send('1:120:30:')

    async def transmite(self, espera=4.0):
        """True si la consola responde a una pulsación dentro del plazo."""
        if self.ws is None:
            return False
        try:
            while True:   # vaciar lo pendiente
                await asyncio.wait_for(self.ws.recv(), 0.2)
        except asyncio.TimeoutError:
            pass
        except Exception:
            return False
        try:
            await self.ws.send('0:1:\n')
            await asyncio.wait_for(self.ws.recv(), espera)
            return True
        except Exception:
            return False

    async def cerrar(self):
        if self.ws is not None:
            try:
                await self.ws.close()
            except Exception:
                pass


def parsear_ct(valor):
    nodo, vmid, pool = valor.split(':')
    return {'nodo': nodo, 'vmid': int(vmid), 'pool': pool}


def retirar(nodos, usuario, fase, pool=None, vmid=None):
    """Ejecuta el procedimiento institucional; las sesiones se terminan en CADA nodo."""
    resultados = {}
    destino = nodos if fase == 'sesiones' else nodos[:1]
    for nodo in destino:
        args = f'--usuario {usuario} --fase {fase} --aplicar'
        if pool:
            args += f' --pool {pool}'
        if vmid:
            args += f' --vmid {vmid}'
        codigo, salida = ssh(nodo, f'bash {SCRIPTS_REMOTOS}/retirar-acceso.sh {args}')
        resultados[nodo] = {'codigo': codigo}
    return resultados


async def esperar_corte(sesion, limite):
    """Mide cuántos segundos tarda la sesión en dejar de transmitir; None si sigue viva al límite."""
    inicio = time.monotonic()
    while time.monotonic() - inicio < limite:
        if not await sesion.transmite(espera=1.5):
            return round(time.monotonic() - inicio, 1)
    return None


async def ensayo(a):
    informe = {'usuario_identidad': 'individual', 'puntos': {}, 'observaciones': {}}
    clave = open(a.clave_archivo).read().strip()
    entrada = a.nodos[0]
    ct, otro = parsear_ct(a.ct), parsear_ct(a.otro_ct)

    # Preparación: ambos pools con el rol de consola (el operador ya creó rol e identidad; se verifica).
    cab = login(entrada, a.usuario, clave)
    if not cab:
        raise SystemExit('no se pudo iniciar sesión con la identidad de ensayo (¿existe y tiene contraseña?)')
    estado, tk_a = Sesion.solicitar(entrada, ct['nodo'], ct['vmid'], cab)
    estado_b, tk_b = Sesion.solicitar(entrada, otro['nodo'], otro['vmid'], cab)
    if estado != 200 or estado_b != 200:
        raise SystemExit('la identidad no puede abrir consola en ambos contenedores; revisar rol y ACL')
    sa, sb = Sesion(entrada, ct['nodo'], ct['vmid'], cab, tk_a), Sesion(entrada, otro['nodo'], otro['vmid'], cab, tk_b)
    await sa.abrir()
    await sb.abrir()
    informe['observaciones']['previo_a_transmite'] = await sa.transmite()
    informe['observaciones']['previo_b_transmite'] = await sb.transmite()
    if not (informe['observaciones']['previo_a_transmite'] and informe['observaciones']['previo_b_transmite']):
        raise SystemExit('las consolas previas no transmiten; el ensayo no es válido')
    guardado = {'cab': dict(cab), 'ticket_a': dict(tk_a), 'url_a': sa.url()}

    # Fase 1: sólo la ACL del pool retirado.
    retirar(a.nodos, a.usuario, 'acl', pool=ct['pool'])
    await asyncio.sleep(2)
    informe['observaciones']['tras_acl_sesion_a_sigue_viva'] = await sa.transmite()
    estado_nueva, _ = Sesion.solicitar(entrada, ct['nodo'], ct['vmid'], cab)
    informe['observaciones']['tras_acl_solicitud_nueva_estado'] = estado_nueva

    # Fase 2: terminar sesiones del contenedor retirado en cada nodo.
    inicio = time.monotonic()
    retirar(a.nodos, a.usuario, 'sesiones', vmid=ct['vmid'])
    corte = await esperar_corte(sa, a.plazo)
    informe['puntos']['1_sesion_abierta_termina'] = {'ok': corte is not None, 'segundos': corte,
        'plazo_s': a.plazo, 'tiempo_total_s': round(time.monotonic() - inicio, 1)}
    informe['observaciones']['otra_sesion_no_afectada'] = await sb.transmite()

    # Punto 2: ticket y solicitud guardados antes del retiro.
    reutil = None
    try:
        sa2 = Sesion(entrada, ct['nodo'], ct['vmid'], guardado['cab'], guardado['ticket_a'])
        await sa2.abrir()
        reutil = await sa2.transmite()
        await sa2.cerrar()
    except Exception:
        reutil = False
    estado_guardado, _ = Sesion.solicitar(entrada, ct['nodo'], ct['vmid'], guardado['cab'])
    informe['puntos']['2_ticket_guardado_rechazado'] = {'ok': (not reutil) and estado_guardado in (401, 403),
        'reconexion_con_ticket_viejo_funciona': bool(reutil), 'solicitud_con_sesion_guardada_estado': estado_guardado}

    # Punto 3: el otro pool sigue vigente con una sesión nueva.
    cab2 = login(entrada, a.usuario, clave)
    estado_o, tk_o = Sesion.solicitar(entrada, otro['nodo'], otro['vmid'], cab2) if cab2 else (0, None)
    nueva_ok = False
    if estado_o == 200:
        sn = Sesion(entrada, otro['nodo'], otro['vmid'], cab2, tk_o)
        try:
            await sn.abrir()
            nueva_ok = await sn.transmite()
        except Exception:
            nueva_ok = False
        await sn.cerrar()
    informe['puntos']['3_otro_pool_conservado'] = {'ok': nueva_ok, 'solicitud_estado': estado_o}

    # Fase 3: eliminar la identidad (retiro total) y comprobar sesiones y tickets restantes.
    retirar(a.nodos, a.usuario, 'identidad')
    retirar(a.nodos, a.usuario, 'sesiones', vmid=otro['vmid'])
    corte_b = await esperar_corte(sb, a.plazo)
    estado_viejo, _ = Sesion.solicitar(entrada, otro['nodo'], otro['vmid'], cab)
    nuevo_login = login(entrada, a.usuario, clave)
    informe['puntos']['4_retiro_total'] = {'ok': corte_b is not None and estado_viejo in (401, 403) and nuevo_login is None,
        'sesion_restante_segundos': corte_b, 'ticket_guardado_estado': estado_viejo,
        'login_nuevo_posible': nuevo_login is not None}
    await sa.cerrar(); await sb.cerrar()

    informe['finalizado_at'] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    informe['aprobado'] = all(p['ok'] for p in informe['puntos'].values())
    informe['nota'] = ('Los puntos 1-3 son los exigidos por FR-007; el 4 documenta el retiro total. Si `aprobado` es falso, '
                       'la consola permanece deshabilitada en esta instalación (FR-008).')
    return informe


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--nodos', nargs='+', required=True, help='direcciones de TODOS los nodos del clúster')
    p.add_argument('--usuario', required=True)
    p.add_argument('--clave-archivo', required=True)
    p.add_argument('--ct', required=True, help='<nodo>:<vmid>:<pool> del contenedor cuyo acceso se retira')
    p.add_argument('--otro-ct', required=True, help='<nodo>:<vmid>:<pool> de otro pool que la persona conserva')
    p.add_argument('--plazo', type=float, default=15.0, help='segundos máximos para el corte de una sesión')
    p.add_argument('--informe', required=True)
    arg = p.parse_args()
    informe = asyncio.run(ensayo(arg))
    with open(arg.informe, 'w') as fh:
        json.dump(informe, fh, indent=2, ensure_ascii=False)
    print(json.dumps(informe, indent=2, ensure_ascii=False))
    sys.exit(0 if informe['aprobado'] else 1)


if __name__ == '__main__':
    main()
