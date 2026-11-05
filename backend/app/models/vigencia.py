from datetime import date, datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.cierre_base import UUIDPrimaryKey, utc_now


class VigenciaAutorizada(UUIDPrimaryKey, Base):
    __tablename__ = 'vigencias_autorizadas'
    __table_args__ = (
        UniqueConstraint('pedido_id', 'revision_decision', name='uq_vigencia_decision'),
        CheckConstraint('inicio_at < fin_exclusivo_at'),
        CheckConstraint('desde_local <= hasta_local'),
        Index('ix_vigencia_cobertura', 'servicio_id', 'inicio_at', 'fin_exclusivo_at'),
        Index('uq_vigencia_sustituye_activa', 'sustituye_id', unique=True,
            postgresql_where=text('sustituye_id IS NOT NULL AND revocada_at IS NULL'),
            sqlite_where=text('sustituye_id IS NOT NULL AND revocada_at IS NULL')),
    )
    pedido_id: Mapped[int] = mapped_column(ForeignKey('pedidos.id'))
    revision_decision: Mapped[int] = mapped_column(Integer)
    servicio_id: Mapped[int | None] = mapped_column(ForeignKey('servicios.id'))
    modalidad: Mapped[str] = mapped_column(String(30))
    anio_lectivo: Mapped[int | None] = mapped_column(Integer)
    calendario_id: Mapped[int | None] = mapped_column(ForeignKey('calendarios_lectivos.id'))
    calendario_revision: Mapped[int | None] = mapped_column(Integer)
    desde_local: Mapped[date] = mapped_column(Date)
    hasta_local: Mapped[date] = mapped_column(Date)
    zona_horaria: Mapped[str] = mapped_column(String(100))
    inicio_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fin_exclusivo_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    aprobado_por: Mapped[int | None] = mapped_column(ForeignKey('usuarios.id'))
    aprobado_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    origen: Mapped[str] = mapped_column(String(20), default='nuevo')
    sustituye_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey('vigencias_autorizadas.id'))
    revocada_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
