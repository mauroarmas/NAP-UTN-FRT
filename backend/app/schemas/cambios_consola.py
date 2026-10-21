from uuid import UUID
from pydantic import Field

from app.schemas.common import Contrato


class ConfirmarRevocacion(Contrato):
    evidencia_ref: UUID


class RegistrarFallo(Contrato):
    motivo: str = Field(min_length=1, max_length=500)
