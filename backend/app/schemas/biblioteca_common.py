"""Contratos administrativos cerrados; respuestas públicas sin contexto sensible."""
from datetime import datetime
from uuid import UUID
from pydantic import Field, StrictInt
from app.schemas.common import Contrato


class RevisionEsperada(Contrato):
    revision_esperada: StrictInt = Field(ge=1)


class Paginacion(Contrato):
    limit: int = Field(default=20, ge=1, le=50)
    cursor: str | None = Field(default=None, max_length=1024)


class TrabajoAceptado(Contrato):
    ensayo_id: UUID
    operacion_id: UUID
    estado: str
    consulta: str
    expires_at: datetime


# Valores de auditoría estables; nunca usar un comando o un secreto como referencia.
AUDIT_ACTIONS = {'incorporar_aplicacion', 'editar_incorporacion', 'crear_revision_biblioteca',
    'iniciar_ensayo', 'confirmar_entradas', 'comprobar_ensayo', 'descartar_ensayo',
    'expirar_ensayo', 'revelar_acceso_ensayo', 'publicar_oferta'}
