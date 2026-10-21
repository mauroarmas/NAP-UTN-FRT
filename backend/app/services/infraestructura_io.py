"""I/O síncrono acotado; vencer la espera no cancela un efecto externo."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Literal

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix='nap-infra')
READ_TIMEOUT = 5
WRITE_TIMEOUT = 10


class InfraNoVerificable(Exception):
    def __init__(self, *, incierto=False):
        super().__init__('No se pudo confirmar el resultado de infraestructura')
        self.incierto = incierto


@dataclass(frozen=True)
class Observacion:
    estado: Literal['presente', 'ausente']
    valor: Any = None


async def ejecutar(function, *args, timeout=READ_TIMEOUT, incierto=False, **kwargs):
    """El pool limita threads reales, incluso si el solicitante deja de esperar.

    wrap_future propaga la cancelación a trabajos que aún no comenzaron. Los
    iniciados conservan su slot hasta terminar y el transporte tiene su plazo.
    Nunca pasar sesiones ORM ni un cliente compartido mutable a esta función.
    """
    future = _executor.submit(function, *args, **kwargs)
    try:
        return await asyncio.wait_for(asyncio.wrap_future(future), timeout)
    except Exception:
        raise InfraNoVerificable(incierto=incierto) from None


async def con_cliente(function, *args, pve=None, timeout=READ_TIMEOUT, incierto=False, **kwargs):
    from app.services.proxmox_client import get_proxmox_factory
    # Capturar antes de encolar: ni configuración mutable ni fixtures que
    # desaparecen mientras una llamada ya vencida sigue terminando en el hilo.
    factory = get_proxmox_factory() if pve is None else None

    def invoke():
        client = factory() if factory else pve
        try:
            return function(client, *args, **kwargs)
        finally:
            if factory and callable(getattr(client, 'close', None)):
                client.close()
    return await ejecutar(invoke, timeout=timeout, incierto=incierto)


async def consultar(method, *args, pve=None, timeout=READ_TIMEOUT, **kwargs):
    def read(client):
        try:
            return Observacion('presente', getattr(client, method)(*args, **kwargs))
        except Exception as exc:
            # 403/500/timeout nunca acreditan ausencia. Proxmox puede responder
            # 500 por un recurso inexistente: requiere reconciliación adicional.
            if getattr(exc, 'status_code', None) == 404:
                return Observacion('ausente')
            raise
    return await con_cliente(read, pve=pve, timeout=timeout)


async def enviar(method, *args, pve=None, timeout=WRITE_TIMEOUT, **kwargs):
    def write(client):
        return getattr(client, method)(*args, **kwargs)
    return await con_cliente(write, pve=pve, timeout=timeout, incierto=True)
