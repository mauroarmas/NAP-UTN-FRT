from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.cierre_base import UUIDPrimaryKey, utc_now


class CambioAccesoConsola(UUIDPrimaryKey, Base):
    __tablename__ = 'cambios_acceso_consola'
    __table_args__ = (
        CheckConstraint("accion IN ('reasignar','retirar','desactivar','cambiar_rol')"),
        CheckConstraint("estado IN ('pendiente','revocacion_fallida','completado')"),
        *[Index('uq_cambio_consola_abierto_' + field, field, unique=True,
                postgresql_where=text("estado IN ('pendiente','revocacion_fallida')"),
                sqlite_where=text("estado IN ('pendiente','revocacion_fallida')"))
          for field in ['usuario_id', 'catedra_id']],
    )
    accion: Mapped[str] = mapped_column(String(20))
    usuario_id: Mapped[int] = mapped_column(ForeignKey('usuarios.id'))
    catedra_id: Mapped[int | None] = mapped_column(ForeignKey('catedras.id'))
    revision_esperada: Mapped[int] = mapped_column(Integer)
    identidad_nativa: Mapped[str | None] = mapped_column(String(200))
    scopes_anteriores: Mapped[list] = mapped_column(JSON, default=list)
    scopes_propuestos: Mapped[list] = mapped_column(JSON, default=list)
    cambio_propuesto: Mapped[dict] = mapped_column(JSON)
    estado: Mapped[str] = mapped_column(String(30), default='pendiente')
    solicitada_por: Mapped[int] = mapped_column(ForeignKey('usuarios.id'))
    solicitada_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    ultimo_error_seguro: Mapped[str | None] = mapped_column(Text)
    evidencia_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey('evidencias.id'))
    completada_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
