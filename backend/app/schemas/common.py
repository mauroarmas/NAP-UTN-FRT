"""Contratos cerrados y unidades del dominio; no aceptan overrides libres."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt


class Contrato(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Recursos(Contrato):
    vcpus: StrictInt = Field(ge=1, le=2**31 - 1)
    ram_mb: StrictInt = Field(ge=1, le=(2**63 - 1) // 1024**2)
    disk_gb: StrictInt = Field(ge=1, le=(2**63 - 1) // 1024**3)

    @property
    def ram_bytes(self):
        return self.ram_mb * 1024**2

    @property
    def disk_bytes(self):
        return self.disk_gb * 1024**3


class Destino(Contrato):
    nodo: str = Field(min_length=1, max_length=100, pattern=r'^[A-Za-z0-9._-]+$')
    storage: str = Field(min_length=1, max_length=100, pattern=r'^[A-Za-z0-9._-]+$')


class SnapshotDecision(Contrato):
    asignacion: Recursos
    destino: Destino
    definicion_version_id: UUID | None = None
    producto: str | None = Field(default=None, max_length=100)


class ErrorDetalle(Contrato):
    codigo: str
    mensaje: str
    reintentable: bool = False
    campos: dict[str, str] = Field(default_factory=dict)
    operation_id: UUID | None = None
