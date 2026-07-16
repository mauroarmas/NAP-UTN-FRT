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
    deployed_at: str | None

    model_config = {"from_attributes": True}


class DesplegarRequest(BaseModel):
    node: str | None = None
    storage: str = "local-lvm"
