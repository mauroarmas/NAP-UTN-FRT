from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.cierre_base import utc_now


class ClaveAccesoServicio(Base):
    """Clave pública SSH de un servicio Linux IaaS; nunca guarda material privado."""
    __tablename__ = 'claves_acceso_servicio'
    __table_args__ = (
        CheckConstraint("tipo IN ('ssh-ed25519','ssh-rsa','ecdsa-sha2-nistp256','ecdsa-sha2-nistp384','ecdsa-sha2-nistp521')", name='ck_clave_acceso_tipo'),
        CheckConstraint('revision >= 1 AND (aplicada_revision IS NULL OR aplicada_revision BETWEEN 1 AND revision)', name='ck_clave_acceso_revisiones'),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    servicio_id: Mapped[int] = mapped_column(ForeignKey('servicios.id'), unique=True)
    tipo: Mapped[str] = mapped_column(String(30))
    clave_publica: Mapped[str] = mapped_column(Text)
    huella_sha256: Mapped[str] = mapped_column(String(60))
    usuario: Mapped[str] = mapped_column(String(32), default='nap', server_default='nap')
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default='1')
    aplicada_revision: Mapped[int | None] = mapped_column(Integer)
    registrada_por_id: Mapped[int | None] = mapped_column(ForeignKey('usuarios.id'))
    registrada_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    aplicada_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
