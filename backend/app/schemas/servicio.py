from datetime import datetime

from pydantic import BaseModel


class ServicioResponse(BaseModel):
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
    # True cuando el `estado` de esta respuesta se confirmó contra Proxmox en
    # esta misma consulta. False significa "último estado conocido": el clúster
    # no respondió o el contenedor no figura en él. No se persiste.
    estado_sincronizado: bool = False
    # True/False según el contenedor figure o no en el clúster; None cuando no
    # se pudo verificar. False significa que alguien lo eliminó por fuera del
    # portal y el registro quedó huérfano. Tampoco se persiste.
    existe_en_proxmox: bool | None = None

    model_config = {"from_attributes": True}


class DesplegarRequest(BaseModel):
    node: str | None = None
    storage: str = "local-lvm"


class ServicioUpdate(BaseModel):
    """Lo poco que se puede editar de un servicio ya desplegado.

    `exento_pausado` lo maneja la cátedra: es ella quien sabe si un servicio sin
    tráfico aparente tiene que seguir encendido. `vence_at` es del administrador,
    porque correr una fecha de fin es una decisión sobre capacidad.
    """

    exento_pausado: bool | None = None
    vence_at: datetime | None = None


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


