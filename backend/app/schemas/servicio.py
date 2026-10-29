from app.schemas.common import Contrato
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator
from typing import Literal


class ServicioResponse(BaseModel):
    periodos_autorizados: list[dict] = Field(default_factory=list)
    cobertura_actual: bool = False
    estado_cobertura: str = 'sin_regularizar'
    proximo_inicio: datetime | None = None
    fin_efectivo_at: datetime | None = None
    confirmado_at: datetime | None = None
    fuente_observacion: str = 'sin_observacion'
    acciones_habilitadas: list[str] = Field(default_factory=list)
    motivo_bloqueo: str | None = None
    regularizacion_pendiente: bool = True
    regularizacion_legacy: bool = False
    operation_id: UUID | None = None
    nombre_snapshot: str | None = None
    modelo_servicio: str | None = None
    disponibilidad_aplicacion: str = 'no_verificada'
    observado_at: datetime | None = None
    id: int
    catedra_id: int
    pedido_id: int | None
    template_id: int
    proxmox_vmid: str | None
    proxmox_node: str | None
    tipo: str
    estado: str
    hostname: str | None
    vcpus_asignados: int
    ram_asignada_mb: int
    disk_asignado_gb: int
    ip_address: str | None
    deployed_at: datetime | None
    deleted_at: datetime | None = None
    # --- Vencimiento y pausado ---
    vence_at: datetime | None = None
    exento_pausado: bool = False
    # Fin del período de gracia: hay una pausa anunciada y todavía evitable.
    pausa_programada_at: datetime | None = None
    # Desde cuándo lo pausó el sistema. Nulo si lo apagó una persona: para la
    # cátedra no es lo mismo "lo apagué yo" que "me lo pausaron".
    pausado_auto_at: datetime | None = None
    # Compatibilidad de lectura: los GET no consultan PVE. La fecha/fuente de
    # observación y confirmado_at permiten valorar la última confirmación.
    estado_sincronizado: bool = False
    # True/False según el contenedor figure o no en el clúster; None cuando no
    # se pudo verificar. False significa que alguien lo eliminó por fuera del
    # portal y el registro quedó huérfano. Tampoco se persiste.
    existe_en_proxmox: bool | None = None

    model_config = {"from_attributes": True}


class DesplegarRequest(BaseModel):
    node: str | None = None
    storage: str = "local-lvm"


class ServicioUpdate(Contrato):
    """Lo poco que se puede editar de un servicio ya desplegado.

    `exento_pausado` lo maneja la cátedra: es ella quien sabe si un servicio sin
    tráfico aparente tiene que seguir encendido. La modificación de vigencias
    crea un pedido auditado y requiere una nueva aprobación.
    """

    exento_pausado: bool | None = None


class ServicioPausadoResponse(BaseModel):
    id: int
    catedra_id: int
    hostname: str | None
    ram_asignada_mb: int
    # El almacenamiento sigue ocupado aunque el cómputo se haya liberado.
    disk_asignado_gb: int
    pausado_auto_at: datetime | None
    dias_pausado: int | None

    model_config = {"from_attributes": True}




from app.schemas.asignacion import VigenciaSolicitud

class DesplegarSnapshotRequest(Contrato):
    """La asignación proviene exclusivamente de la decisión aprobada."""
    pass


class OrdenServicioRequest(Contrato):
    motivo: str | None = Field(default=None, max_length=500)


class RenovacionRequest(Contrato):
    vigencia: VigenciaSolicitud


class ModificacionVigenciaRequest(RenovacionRequest):
    sustituye_vigencia_id: UUID
    motivo: str = Field(min_length=1, max_length=2000)


class RevelarAccesoRequest(Contrato):
    pass


class AccesoServicioResponse(Contrato):
    servicio_id: int
    modelo_servicio: str | None = None
    producto: str | None = None
    disponibilidad: str
    verificado_at: datetime | None = None
    metodo: Literal['consola', 'postgresql', 'https', 'mariadb'] | None = None
    direccion: str | None = None
    puerto: int | None = None
    puede_revelar_credenciales: bool
    estado_entrega: Literal['no_preparado', 'solo_validacion', 'pendiente_verificacion', 'entregado', 'no_disponible']
    instrucciones: str
    acceso_con_nap: bool = False
    puede_abrir_con_nap: bool = False
    verificacion_instancia: dict | None = None


class AccesoReveladoResponse(Contrato):
    servicio_id: int
    estado_entrega: Literal['solo_validacion', 'entregado']
    metodo: Literal['consola', 'postgresql', 'https', 'mariadb']
    direccion: str
    credenciales: dict[str, str | int]
    instrucciones: str


class VerificarAccesoRequest(Contrato):
    evidencia_ref: UUID
    endpoint: str = Field(min_length=1, max_length=2048)
    observado_at: str = Field(min_length=20, max_length=40)

    @field_validator('observado_at')
    @classmethod
    def instante_utc(cls, value):
        if not value.endswith('Z') or datetime.fromisoformat(value.replace('Z', '+00:00')).tzinfo is None:
            raise ValueError('Indicá el instante UTC con Z del documento de evidencia')
        return value
