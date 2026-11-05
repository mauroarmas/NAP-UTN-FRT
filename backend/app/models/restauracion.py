"""Control de recuperación separado de las cuentas y su segundo factor."""
from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, JSON, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.cierre_base import UUIDPrimaryKey, utc_now


class Restauracion(UUIDPrimaryKey, Base):
    __tablename__ = 'restauraciones'
    referencia: Mapped[str] = mapped_column(String(200), unique=True)
    operador: Mapped[str] = mapped_column(String(200))
    estado: Mapped[str] = mapped_column(String(20), default='pendiente')
    preparada_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    resumen: Mapped[dict] = mapped_column(JSON)
    habilitada_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    habilitada_por: Mapped[str | None] = mapped_column(String(200))
    prueba_referencia: Mapped[str | None] = mapped_column(String(200))
    prueba_sha256: Mapped[str | None] = mapped_column(String(64))
    estado_sha256: Mapped[str | None] = mapped_column(String(64))
    __table_args__ = (
        CheckConstraint("estado IN ('pendiente','habilitada')", name='ck_restauracion_estado'),
        CheckConstraint("estado != 'habilitada' OR (habilitada_at IS NOT NULL AND habilitada_por IS NOT NULL "
                        "AND prueba_referencia IS NOT NULL AND prueba_sha256 IS NOT NULL AND estado_sha256 IS NOT NULL)",
                        name='ck_restauracion_habilitada'),
        Index('uq_restauracion_pendiente', 'estado', unique=True,
              postgresql_where=text("estado = 'pendiente'"), sqlite_where=text("estado = 'pendiente'")),
    )


class AccesoInicialRestaurado(UUIDPrimaryKey, Base):
    __tablename__ = 'accesos_iniciales_restaurados'
    restauracion_id: Mapped[UUID] = mapped_column(ForeignKey('restauraciones.id'))
    usuario_id: Mapped[int] = mapped_column(ForeignKey('usuarios.id'), index=True)
    creado_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    reemitido_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reemitido_por: Mapped[str | None] = mapped_column(String(200))
    referencia: Mapped[str | None] = mapped_column(String(200))
    __table_args__ = (
        UniqueConstraint('restauracion_id', 'usuario_id', name='uq_acceso_restaurado_usuario'),
        CheckConstraint('reemitido_at IS NULL OR (reemitido_por IS NOT NULL AND referencia IS NOT NULL)',
                        name='ck_acceso_restaurado_reemision'),
    )
