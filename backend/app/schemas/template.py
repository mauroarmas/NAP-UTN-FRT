from pydantic import BaseModel


class TemplateBase(BaseModel):
    nombre: str
    descripcion: str | None = None
    tipo: str = "lxc"
    default_vcpus: int = 1
    default_ram_mb: int = 256
    default_disk_gb: int = 2
    os_template: str | None = None
    config_extra: dict | None = None


class TemplateCreate(TemplateBase):
    pass


class TemplateResponse(TemplateBase):
    id: int
    activo: bool

    model_config = {"from_attributes": True}
