from pydantic import BaseModel
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
    titular_id: int | None = None


class CatedraUpdate(BaseModel):
    nombre: str | None = None
    descripcion: str | None = None
    titular_id: int | None = None
    activa: bool | None = None


class CatedraResponse(CatedraBase):
    id: int
    activa: bool
    created_at: datetime
    titular_id: int | None = None
    titular: TitularBreve | None = None

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
