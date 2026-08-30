"""Registro de transiciones, con o sin persona detrás.

La constitución exige que toda transición quede registrada con su autor. Algunas
las ejecuta el sistema —expirar una reserva, aplicar un vencimiento, pausar por
inactividad— y no tienen persona que las haya decidido.

``usuario_id = NULL`` es exactamente eso: el sistema. No se inventa un usuario
centinela (contaminaría el listado de personas y podría recibir login) ni se
omite el registro (dejaría transiciones invisibles).
"""

from app.models.pedido import PedidoHistorial
from app.models.servicio_historial import ServicioHistorial
from app.models.usuario import Usuario

AUTOR_SISTEMA = "sistema"


def registrar_pedido(
    pedido_id: int,
    estado_anterior: str,
    estado_nuevo: str,
    comentario: str | None = None,
    usuario: Usuario | None = None,
) -> PedidoHistorial:
    """Construye la entrada de historial de un pedido. No hace commit."""
    return PedidoHistorial(
        pedido_id=pedido_id,
        estado_anterior=estado_anterior,
        estado_nuevo=estado_nuevo,
        comentario=comentario,
        usuario_id=usuario.id if usuario else None,
    )


def registrar_servicio(
    servicio_id: int,
    estado_anterior: str,
    estado_nuevo: str,
    comentario: str | None = None,
    usuario: Usuario | None = None,
) -> ServicioHistorial:
    """Construye la entrada de historial de un servicio. No hace commit."""
    return ServicioHistorial(
        servicio_id=servicio_id,
        estado_anterior=estado_anterior,
        estado_nuevo=estado_nuevo,
        comentario=comentario,
        usuario_id=usuario.id if usuario else None,
    )


def autor_display(registro) -> str:
    """Nombre a mostrar para el autor de una entrada de historial."""
    if registro.usuario_id is None:
        return AUTOR_SISTEMA
    usuario = getattr(registro, "usuario", None)
    return usuario.nombre if usuario else str(registro.usuario_id)
