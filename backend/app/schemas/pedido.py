from pydantic import BaseModel, Field, StrictInt, model_validator
from datetime import datetime
from typing import Literal
from uuid import UUID
from app.schemas.common import Contrato
from app.schemas.asignacion import VigenciaSolicitud


class CatedraBreve(BaseModel):
    """Identificación mínima de la cátedra, para rotular filas.

    Con una persona que puede tener varias cátedras, cada pedido y cada servicio
    tiene que decir a cuál pertenece: si no, el listado es ambiguo.
    """

    id: int
    nombre: str

    model_config = {"from_attributes": True}


class DatosSolicitud(Contrato):
    titulo: str | None = Field(default=None, max_length=200)
    software_solicitado: str | None = Field(default=None, max_length=200)


class PedidoCreate(Contrato):
    oferta_revision: StrictInt | None = Field(default=None, ge=1)
    template_id: StrictInt | None = Field(default=None, ge=1)
    modelo_servicio: Literal['iaas', 'paas', 'saas']
    descripcion_requerimientos: str | None = Field(default=None, max_length=5000)
    vigencia: VigenciaSolicitud
    catedra_id: StrictInt | None = Field(default=None, ge=1)
    parametros_extra: DatosSolicitud | None = None

    @model_validator(mode='after')
    def validar_servicio_a_medida(self):
        if self.template_id is None:
            if self.modelo_servicio == 'iaas':
                raise ValueError('Para infraestructura, seleccioná una plantilla del catálogo')
            if not self.parametros_extra or not (self.parametros_extra.software_solicitado or '').strip():
                raise ValueError('Indicá qué software o servicio necesitás al elegir Otro')
            if not (self.descripcion_requerimientos or '').strip():
                raise ValueError('Describí el uso y la justificación pedagógica del servicio solicitado')
        return self


class PedidoCambiarEstado(BaseModel):
    nuevo_estado: str
    comentario: str | None = None
    motivo_rechazo: str | None = None


from app.schemas.asignacion import AprobacionEfectiva as PedidoAprobar, SeleccionEvaluacion as PedidoEvaluacion


class PedidoSolicitarAjuste(Contrato):
    observaciones: str = Field(min_length=1, max_length=2000)


class PedidoReenviar(Contrato):
    oferta_revision: StrictInt | None = Field(default=None, ge=1)
    template_id: StrictInt | None = Field(default=None, ge=1)
    modelo_servicio: Literal['iaas', 'paas', 'saas'] | None = None
    descripcion_requerimientos: str | None = Field(default=None, max_length=5000)
    vigencia: VigenciaSolicitud
    parametros_extra: DatosSolicitud | None = None


class PedidoCancelar(Contrato):
    motivo: str = Field(min_length=1, max_length=2000)


class PedidoRechazar(Contrato):
    motivo: str = Field(min_length=1, max_length=2000)


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


class CompromisoPedidoResponse(Contrato):
    estado: Literal['reservado','materializado','incierto']
    vcpus_retenidos: int = Field(ge=0)
    ram_mb_retenida: int = Field(ge=0)
    disk_bytes_retenidos: int = Field(ge=0)
    expira_at: datetime | None = None


class PedidoResponse(BaseModel):
    compromiso_capacidad: CompromisoPedidoResponse | None = None
    operation_id: UUID | None = None
    vigencia: dict | None = None
    vigencia_aprobada: dict | None = None
    despliegue_habilitado: bool = False
    anio_lectivo: int | None = None
    revision: int = 1
    revision_decision: int = 0
    definicion_version_id: UUID | None = None
    sustituye_vigencia_id: UUID | None = None
    seleccion_oferta_snapshot: dict | None = None
    asignacion_snapshot: dict | None = None
    destino_snapshot: dict | None = None
    decision_snapshot: dict | None = None
    id: int
    catedra_id: int
    catedra: CatedraBreve | None = None
    solicitante_id: int
    template_id: int | None = None
    modelo_servicio: str = "iaas"
    descripcion_requerimientos: str | None = None
    vigencia_tipo: str = "primer_cuatrimestre"
    vigencia_desde: datetime | None = None
    vigencia_hasta: datetime | None = None
    observaciones_ajuste: str | None = None
    opciones_avanzadas: dict | None = None
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
