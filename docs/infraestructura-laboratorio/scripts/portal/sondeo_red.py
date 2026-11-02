"""Sondeo TCP de salida: se ejecuta DENTRO de una instancia (python3 viene en la plantilla) para ver qué puede alcanzar.

  sondeo_red.py etiqueta,host,puerto [etiqueta,host,puerto ...]

Informa ALCANZA, rechazado (RST) o bloqueado (sin respuesta). Lo lanza sondear-red.sh; no usar contra redes ajenas.
"""
import socket
import sys


def sondear(host, puerto, espera=4):
    conexion = socket.socket(); conexion.settimeout(espera)
    try:
        conexion.connect((host, int(puerto))); return 'ALCANZA'
    except socket.timeout:
        return 'bloqueado (sin respuesta)'
    except ConnectionRefusedError:
        return 'rechazado (RST)'
    except OSError as error:
        return 'bloqueado (%s)' % error.strerror
    finally:
        conexion.close()


if __name__ == '__main__':
    for destino in sys.argv[1:]:
        etiqueta, host, puerto = destino.split(',')
        print('   %-24s %s:%s -> %s' % (etiqueta, host, puerto, sondear(host, puerto)))
