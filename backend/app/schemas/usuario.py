from pydantic import BaseModel, ConfigDict, Field, EmailStr, StrictInt, field_validator
from typing import Literal, Annotated
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
    model_config = ConfigDict(extra='forbid')
    username: str = Field(min_length=1, max_length=50, pattern=r'^[A-Za-z0-9_.-]+$')
    nombre: str = Field(min_length=1, max_length=100)
    email: EmailStr = Field(max_length=100)
    rol: Literal['admin', 'catedra_admin'] = 'catedra_admin'
    password: None = None
    # Las cátedras se asignan en el mismo acto que el alta: crear la persona y
    # después acordarse de asignarle sus materias es el paso que se olvida.
    catedra_ids: list[Annotated[StrictInt, Field(ge=1)]] = Field(default_factory=list)

    @field_validator('nombre', mode='before')
    @classmethod
    def strip_name(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator('email', 'username')
    @classmethod
    def canonical(cls, value):
        return value.casefold()


class UsuarioUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision_esperada: StrictInt | None = Field(default=None, ge=1)
    nombre: str | None = Field(default=None, min_length=1, max_length=100)
    email: EmailStr | None = Field(default=None, max_length=100)
    rol: Literal['admin', 'catedra_admin'] | None = None
    # Lista completa de cátedras a cargo tras la edición: las que no estén acá
    # quedan sin titular. `None` significa "no tocar la titularidad".
    catedra_ids: list[Annotated[StrictInt, Field(ge=1)]] | None = None
    activo: bool | None = None
    recibir_notificaciones_email: bool | None = None
    nueva_password: str | None = None

    @field_validator('nombre', 'email', 'rol', 'activo', 'recibir_notificaciones_email')
    @classmethod
    def explicit_required(cls, value):
        if value is None or isinstance(value, str) and not value.strip():
            raise ValueError('El campo no puede quedar vacío')
        return value.strip() if isinstance(value, str) else value

    @field_validator('email')
    @classmethod
    def canonical_email(cls, value):
        return value.casefold()


class UsuarioResponse(UsuarioBase):
    id: int
    activo: bool
    debe_cambiar_password: bool = False
    recibir_notificaciones_email: bool = True
    totp_habilitado: bool
    created_at: datetime
    catedras: list[CatedraBreve] = []
    revision_admin: int = 1
    inventario_consola: str = 'desconocido'

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
