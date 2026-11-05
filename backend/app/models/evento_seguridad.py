from datetime import datetime

from sqlalchemy import String, ForeignKey, DateTime, event
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.cierre_base import UUIDPrimaryKey, utc_now


class EventoSeguridad(UUIDPrimaryKey, Base):
    __tablename__ = 'eventos_seguridad'
    usuario_objetivo_id: Mapped[int | None] = mapped_column(ForeignKey('usuarios.id'), index=True)
    actor_usuario_id: Mapped[int | None] = mapped_column(ForeignKey('usuarios.id'))
    actor_institucional: Mapped[str | None] = mapped_column(String(200))
    accion: Mapped[str] = mapped_column(String(80))
    resultado: Mapped[str] = mapped_column(String(20))
    motivo: Mapped[str | None] = mapped_column(String(500))
    referencia: Mapped[str | None] = mapped_column(String(200))
    creado_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    request_id: Mapped[str | None] = mapped_column(String(80))


@event.listens_for(EventoSeguridad, 'before_update')
@event.listens_for(EventoSeguridad, 'before_delete')
def no_modify_event(mapper, connection, target):
    raise ValueError('Los eventos de seguridad son inmutables')
