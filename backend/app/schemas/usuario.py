from pydantic import BaseModel
from datetime import datetime


class UsuarioBase(BaseModel):
    username: str
    email: str | None = None
    nombre: str
    rol: str = "catedra_admin"
    catedra_id: int | None = None


class UsuarioCreate(UsuarioBase):
    password: str


class UsuarioResponse(UsuarioBase):
    id: int
    activo: bool
    totp_habilitado: bool
    created_at: datetime

    model_config = {"from_attributes": True}
