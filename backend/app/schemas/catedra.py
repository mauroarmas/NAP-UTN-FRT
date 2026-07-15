from pydantic import BaseModel
from datetime import datetime


class CatedraBase(BaseModel):
    nombre: str
    descripcion: str | None = None
    cuota_vcpus: int = 2
    cuota_ram_mb: int = 1024
    cuota_storage_gb: int = 8


class CatedraCreate(CatedraBase):
    pass


class CatedraUpdate(BaseModel):
    nombre: str | None = None
    descripcion: str | None = None
    cuota_vcpus: int | None = None
    cuota_ram_mb: int | None = None
    cuota_storage_gb: int | None = None
    activa: bool | None = None


class CatedraResponse(CatedraBase):
    id: int
    activa: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class CatedraConUso(CatedraResponse):
    """Cátedra con información de uso actual de recursos."""
    vcpus_en_uso: int = 0
    ram_en_uso_mb: int = 0
    storage_en_uso_gb: int = 0
    servicios_activos: int = 0
