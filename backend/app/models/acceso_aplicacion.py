from datetime import datetime
from uuid import UUID
from sqlalchemy import DateTime, ForeignKey, String, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models.cierre_base import UUIDPrimaryKey


class AccesoAplicacion(UUIDPrimaryKey, Base):
    """Código de apertura de un uso; sólo se conserva su hash."""
    __tablename__ = 'accesos_aplicacion'
    codigo_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    sesion_id: Mapped[UUID] = mapped_column(ForeignKey('sesiones_autenticacion.id'), index=True)
    servicio_id: Mapped[int] = mapped_column(ForeignKey('servicios.id'), index=True)
    creado_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expira_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumido_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (Index('ix_acceso_aplicacion_expira', 'expira_at'),)
