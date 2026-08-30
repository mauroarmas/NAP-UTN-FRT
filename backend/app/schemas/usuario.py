from pydantic import BaseModel
from datetime import datetime


class CatedraBreve(BaseModel):
    id: int
    nombre: str


class UsuarioBase(BaseModel):
    username: str
    email: str | None = None
    nombre: str
    rol: str = "catedra_admin"


class UsuarioCreate(UsuarioBase):
    password: str
    # Las cátedras se asignan en el mismo acto que el alta: crear la persona y
    # después acordarse de asignarle sus materias es el paso que se olvida.
    catedra_ids: list[int] = []


class UsuarioUpdate(BaseModel):
    nombre: str | None = None
    email: str | None = None
    rol: str | None = None
    # Lista completa de cátedras a cargo tras la edición: las que no estén acá
    # quedan sin titular. `None` significa "no tocar la titularidad".
    catedra_ids: list[int] | None = None
    activo: bool | None = None
    nueva_password: str | None = None


class UsuarioResponse(UsuarioBase):
    id: int
    activo: bool
    totp_habilitado: bool
    created_at: datetime
    catedras: list[CatedraBreve] = []

    model_config = {"from_attributes": True}


class UsuarioRetiroResponse(BaseModel):
    """Resultado de retirar una persona.

    `resultado` distingue los dos desenlaces posibles para que la interfaz pueda
    decir qué pasó de verdad: quien ejecuta la acción no tiene que saber de
    antemano si la cuenta tenía historial o no.
    """

    id: int
    username: str
    resultado: str  # "desactivado" | "eliminado"
    mensaje: str
