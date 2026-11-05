from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, event
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.cierre_base import UUIDPrimaryKey, utc_now


class Evidencia(UUIDPrimaryKey, Base):
    __tablename__ = 'evidencias'
    __table_args__ = (
        CheckConstraint("tipo IN ('acceso_instancia','validacion_definicion','revocacion_consola')"),
        CheckConstraint('schema_version = 1'),
        Index('ix_evidencias_tipo_fecha', 'tipo', 'registrada_at'),
    )
    tipo: Mapped[str] = mapped_column(String(30))
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    documento_canonico: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    registrada_por: Mapped[int] = mapped_column(ForeignKey('usuarios.id'))
    registrada_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


@event.listens_for(Evidencia, 'before_update')
@event.listens_for(Evidencia, 'before_delete')
def prevent_evidence_mutation(mapper, connection, target):
    raise ValueError('La evidencia es inmutable')
