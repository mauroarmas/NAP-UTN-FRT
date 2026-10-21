from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint, JSON, event
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.cierre_base import utc_now


class CalendarioLectivo(Base):
    __tablename__ = 'calendarios_lectivos'
    id: Mapped[int] = mapped_column(primary_key=True)
    anio: Mapped[int] = mapped_column(Integer, unique=True)
    zona_horaria: Mapped[str] = mapped_column(String(100), default='America/Argentina/Tucuman')
    revision: Mapped[int] = mapped_column(Integer, default=1)
    actualizado_por: Mapped[int | None] = mapped_column(ForeignKey('usuarios.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class PeriodoCalendario(Base):
    __tablename__ = 'periodos_calendario'
    __table_args__ = (UniqueConstraint('calendario_id', 'tipo', name='uq_calendario_tipo'),
                      CheckConstraint('desde <= hasta'),
                      CheckConstraint("tipo IN ('primer_cuatrimestre','segundo_cuatrimestre','anual')"))
    id: Mapped[int] = mapped_column(primary_key=True)
    calendario_id: Mapped[int] = mapped_column(ForeignKey('calendarios_lectivos.id'))
    tipo: Mapped[str] = mapped_column(String(30))
    desde: Mapped[date] = mapped_column(Date)
    hasta: Mapped[date] = mapped_column(Date)


class CalendarioHistorial(Base):
    __tablename__ = 'calendarios_historial'
    __table_args__ = (UniqueConstraint('calendario_id', 'revision', name='uq_calendario_historial_revision'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    calendario_id: Mapped[int] = mapped_column(ForeignKey('calendarios_lectivos.id'))
    revision: Mapped[int] = mapped_column(Integer)
    actor_usuario_id: Mapped[int] = mapped_column(ForeignKey('usuarios.id'))
    anterior: Mapped[dict | None] = mapped_column(JSON)
    nuevo: Mapped[dict] = mapped_column(JSON)
    creado_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


@event.listens_for(CalendarioHistorial, 'before_update')
@event.listens_for(CalendarioHistorial, 'before_delete')
def immutable_history(*args):
    raise ValueError('El historial del calendario es de solo agregado')
