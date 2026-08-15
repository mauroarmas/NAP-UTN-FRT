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


class ConsolaTicketResponse(BaseModel):
    ticket: str
    expira_en_segundos: int
