from datetime import datetime
from typing import Literal
from uuid import UUID
from app.schemas.common import Contrato


class OperacionResponse(Contrato):
    operation_id: UUID
    tipo: Literal['desplegar', 'iniciar', 'detener', 'reiniciar', 'pausar', 'eliminar', 'reparar']
    estado: Literal['pendiente', 'en_curso', 'confirmada', 'fallida', 'incierta']
    fase: str
    pedido_id: int | None
    servicio_id: int | None
    intento: int
    error_codigo: str | None
    error_detalle_seguro: str | None
    creado_at: datetime
    updated_at: datetime
    confirmada_at: datetime | None
    next_poll_at: datetime
