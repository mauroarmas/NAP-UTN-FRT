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
from sqlalchemy import event
from app.services.idempotencia_service import safe_json
from app.utils.clock import clock
import json

AUTOR_SISTEMA = "sistema"


def registrar_pedido(
    pedido_id: int,
    estado_anterior: str,
    estado_nuevo: str,
    comentario: str | None = None,
    usuario: Usuario | None = None,
    operacion_id=None,
    evento_clave=None,
    metadata=None,
) -> PedidoHistorial:
    """Construye la entrada de historial de un pedido. No hace commit."""
    return PedidoHistorial(
        pedido_id=pedido_id,
        estado_anterior=estado_anterior,
        estado_nuevo=estado_nuevo,
        comentario=comentario,
        usuario_id=usuario.id if usuario else None,
        actor_tipo='usuario' if usuario else 'sistema',
        operacion_id=operacion_id,
        evento_clave=evento_clave,
        decision_metadata=json.loads(safe_json(metadata)) if metadata is not None else None,
    )


def registrar_servicio(
    servicio_id: int,
    estado_anterior: str,
    estado_nuevo: str,
    comentario: str | None = None,
    usuario: Usuario | None = None,
    operacion_id=None,
    evento_clave=None,
    metadata=None,
) -> ServicioHistorial:
    """Construye la entrada de historial de un servicio. No hace commit."""
    return ServicioHistorial(
        servicio_id=servicio_id,
        estado_anterior=estado_anterior,
        estado_nuevo=estado_nuevo,
        comentario=comentario,
        usuario_id=usuario.id if usuario else None,
        actor_tipo='usuario' if usuario else 'sistema',
        operacion_id=operacion_id,
        evento_clave=evento_clave,
        decision_metadata=json.loads(safe_json(metadata)) if metadata is not None else None,
        created_at=clock.now().replace(tzinfo=None),
    )


def asignacion_historica(service):
    """Valores confirmados del servicio en este evento, sin releer el catálogo."""
    return {'catedra_id': service.catedra_id, 'modelo_servicio': service.modelo_servicio,
        'asignacion': {'vcpus': service.vcpus_asignados, 'ram_mb': service.ram_asignada_mb,
            'disk_gb': service.disk_asignado_gb}}


def autor_display(registro) -> str:
    """Nombre a mostrar para el autor de una entrada de historial."""
    if registro.usuario_id is None:
        return AUTOR_SISTEMA
    usuario = getattr(registro, "usuario", None)
    return usuario.nombre if usuario else str(registro.usuario_id)


def prevent_history_mutation(mapper, connection, target):
    raise ValueError('El historial es de solo agregado')


for model in (PedidoHistorial, ServicioHistorial):
    event.listen(model, 'before_update', prevent_history_mutation)
    event.listen(model, 'before_delete', prevent_history_mutation)
