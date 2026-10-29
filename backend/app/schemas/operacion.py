from datetime import datetime
from typing import Literal
from uuid import UUID
from app.schemas.common import Contrato


class OperacionResponse(Contrato):
    operation_id: UUID
    tipo: Literal['desplegar', 'iniciar', 'detener', 'reiniciar', 'pausar', 'eliminar', 'reparar']
    estado: Literal['pendiente', 'en_curso', 'confirmada', 'fallida', 'incierta']
    fase: str
    fase_aplicacion: str | None = None
    actividad_aplicacion_at: datetime | None = None
    reintento_disponible: bool | None = None
    motivo_compatibilidad: str | None = None
    pedido_id: int | None
    servicio_id: int | None
    intento: int
    error_codigo: str | None
    error_detalle_seguro: str | None
    creado_at: datetime
    updated_at: datetime
    confirmada_at: datetime | None
    next_poll_at: datetime


class ConsolaItemResponse(Contrato):
    seq: int
    intento: int
    captured_at: datetime
    fase: str
    stream: str
    texto_depurado: str


class ConsolaOperacionResponse(Contrato):
    operation_id: UUID
    operacion_raiz_id: UUID
    estado: str
    fase: str
    intento_efectivo: int
    items: list[ConsolaItemResponse]
    next_cursor: int | None
    previous_cursor: int | None
    has_more: bool
    first_retained_seq: int
    last_seq: int
    truncated: bool
    expired: bool
    dropped_messages: int
    last_captured_at: datetime | None
    last_ingested_at: datetime | None
    resultado_final: dict | None

