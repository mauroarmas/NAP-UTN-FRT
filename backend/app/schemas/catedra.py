from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator
from datetime import datetime


class TitularBreve(BaseModel):
    """Quién responde por la cátedra.

    Va anidado en toda respuesta porque el nombre solo dejó de alcanzar para
    identificarla: dos personas pueden dictar materias homónimas.
    """

    id: int
    nombre: str
    username: str


class CatedraBase(BaseModel):
    nombre: str
    descripcion: str | None = None


class CatedraCreate(CatedraBase):
    model_config = ConfigDict(extra='forbid')
    nombre: str = Field(min_length=1, max_length=100)
    descripcion: str | None = Field(default=None, max_length=2000)
    titular_id: StrictInt | None = Field(default=None, ge=1)

    @field_validator('nombre', mode='before')
    @classmethod
    def strip_name(cls, value):
        return value.strip() if isinstance(value, str) else value


class CatedraUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision_esperada: StrictInt | None = Field(default=None, ge=1)
    nombre: str | None = Field(default=None, min_length=1, max_length=100)
    descripcion: str | None = Field(default=None, max_length=2000)
    titular_id: StrictInt | None = Field(default=None, ge=1)
    activa: bool | None = None

    @field_validator('nombre', 'activa')
    @classmethod
    def explicit_required(cls, value):
        if value is None or isinstance(value, str) and not value.strip():
            raise ValueError('El campo no puede quedar vacío')
        return value.strip() if isinstance(value, str) else value


class CatedraResponse(CatedraBase):
    id: int
    activa: bool
    created_at: datetime
    titular_id: int | None = None
    titular: TitularBreve | None = None
    revision_admin: int = 1

    model_config = {"from_attributes": True}


class CatedraConUso(CatedraResponse):
    """Cátedra con su consumo vigente.

    Sin denominador: ya no hay techo declarado contra el cual compararlo. Lo
    que la cátedra necesita saber es qué tiene desplegado y cuánto ocupa.
    """

    vcpus_en_uso: int = 0
    ram_en_uso_mb: int = 0
    storage_en_uso_gb: int = 0
    servicios_activos: int = 0
