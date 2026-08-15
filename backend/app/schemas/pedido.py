from pydantic import BaseModel
from datetime import datetime


class PedidoCreate(BaseModel):
    template_id: int
    parametros_extra: dict | None = None


class PedidoCambiarEstado(BaseModel):
    nuevo_estado: str
    comentario: str | None = None
    motivo_rechazo: str | None = None


class PedidoResponse(BaseModel):
    id: int
    catedra_id: int
    solicitante_id: int
    template_id: int
    estado: str
    motivo_rechazo: str | None
    parametros_extra: dict | None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
    vmid_reservado: str | None = None
    deleted_at: datetime | None = None

    model_config = {"from_attributes": True}


class PedidoHistorialResponse(BaseModel):
    id: int
    estado_anterior: str
    estado_nuevo: str
    comentario: str | None
    usuario_id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class PedidoDetalleResponse(PedidoResponse):
    historial: list[PedidoHistorialResponse] = []
