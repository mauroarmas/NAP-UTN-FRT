"""Diagnóstico seguro de excepciones: tipo, cadena de causas y ubicación; nunca el mensaje.

El texto de una excepción puede contener valores privados (credenciales, rutas, direcciones), por eso
sólo se registran los nombres de los tipos y el archivo/línea/función del punto de falla. No se incluyen
argumentos, variables locales ni la traza completa.
"""
import re
import traceback

_RUTA = re.compile(r'(?:^|/)((?:app|infra)/.+)$')


def _tipos(exc, limite=4):
    tipos, vistos = [], set()
    while exc is not None and len(tipos) < limite and id(exc) not in vistos:
        vistos.add(id(exc))
        tipos.append(type(exc).__name__)
        exc = exc.__cause__ or exc.__context__
    return tipos


def _ubicacion(exc):
    marcos = traceback.extract_tb(exc.__traceback__) if exc.__traceback__ else []
    propios = [m for m in marcos if _RUTA.search(m.filename.replace('\\', '/'))]
    marco = (propios or marcos or [None])[-1]
    if marco is None:
        return 'sin traza'
    ruta = _RUTA.search(marco.filename.replace('\\', '/'))
    nombre = ruta.group(1) if ruta else marco.filename.rsplit('/', 1)[-1]
    if nombre.startswith('app/app/'):  # el contenedor monta el código en /app/app
        nombre = nombre[4:]
    return f"{nombre}:{marco.lineno} {marco.name}"


def resumen_excepcion(exc):
    """Ej.: 'InfraNoVerificable <- TimeoutError en app/services/x.py:42 consultar'."""
    return f"{' <- '.join(_tipos(exc))} en {_ubicacion(exc)}"
