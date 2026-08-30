from pydantic import BaseModel
from datetime import datetime


class CatedraBreve(BaseModel):
    """Identificación mínima de la cátedra, para rotular filas.

    Con una persona que puede tener varias cátedras, cada pedido y cada servicio
    tiene que decir a cuál pertenece: si no, el listado es ambiguo.
    """

    id: int
    nombre: str

    model_config = {"from_attributes": True}


class PedidoCreate(BaseModel):
    template_id: int
    # Requerido solo si la persona tiene más de una cátedra; con una sola se
    # asume y no se le pide.
    catedra_id: int | None = None
    parametros_extra: dict | None = None


class PedidoCambiarEstado(BaseModel):
    nuevo_estado: str
    comentario: str | None = None
    motivo_rechazo: str | None = None


class PedidoAprobar(BaseModel):
    # Huella de la capacidad que se le mostró al administrador. Si cambió desde
    # entonces, la aprobación se rechaza y hay que confirmar sobre los valores
    # vigentes.
    capacidad_token: str | None = None
    # Obligatoria solo si la aprobación excede la capacidad libre.
    justificacion_capacidad: str | None = None


class PedidoRechazar(BaseModel):
    motivo: str


class PedidoRevertir(BaseModel):
    """Deshacer una aprobación. El motivo es obligatorio y lo ve la cátedra.

    El campo se declara opcional a propósito, aunque no lo sea: si Pydantic lo
    rechazara por su cuenta, un motivo ausente daría 422 y uno en blanco 400,
    dos códigos distintos para el mismo error de quien llama. La validación vive
    en el servicio, junto a la de `rechazar`, y siempre responde 400.
    """

    motivo: str | None = None


class CapacidadLiberada(BaseModel):
    """Lo que una reversión devolvió al saldo libre del clúster."""

    vcpus: int
    ram_mb: int
    storage_gb: int


class PedidoResponse(BaseModel):
    id: int
    catedra_id: int
    catedra: CatedraBreve | None = None
    solicitante_id: int
    template_id: int
    estado: str
    tipo: str = "alta"
    servicio_id: int | None = None
    motivo_rechazo: str | None
    parametros_extra: dict | None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
    vmid_reservado: str | None = None
    deleted_at: datetime | None = None
    reserva_vcpus: int = 0
    reserva_ram_mb: int = 0
    reserva_disk_gb: int = 0
    reserva_expira_at: datetime | None = None
    justificacion_capacidad: str | None = None

    model_config = {"from_attributes": True}


class PedidoHistorialResponse(BaseModel):
    id: int
    estado_anterior: str
    estado_nuevo: str
    comentario: str | None
    # Nulo cuando la transición la ejecutó el sistema.
    usuario_id: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PedidoDetalleResponse(PedidoResponse):
    historial: list[PedidoHistorialResponse] = []


class PedidoRevertidoResponse(PedidoDetalleResponse):
    """Detalle del pedido más cuánta capacidad volvió a estar libre.

    Se informa acá para que la interfaz pueda decirlo en el acto, sin una
    segunda consulta a capacidad que además podría leer otro número si alguien
    aprobó en el medio.
    """

    capacidad_liberada: CapacidadLiberada | None = None
