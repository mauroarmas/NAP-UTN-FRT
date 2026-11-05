from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.cierre_base import UUIDPrimaryKey, utc_now


class ReservaRedAplicacion(UUIDPrimaryKey, Base):
    __tablename__ = 'reservas_red_aplicacion'
    __table_args__ = (
        CheckConstraint('perfil_revision > 0', name='ck_red_revision'),
        Index('uq_red_direccion_activa', 'cluster_id', 'address', unique=True,
            postgresql_where=text('liberada_at IS NULL'), sqlite_where=text('liberada_at IS NULL')),
        Index('uq_red_slot_activo', 'perfil_id', 'slot_id', unique=True,
            postgresql_where=text('liberada_at IS NULL'), sqlite_where=text('liberada_at IS NULL')),
    )
    identidad_id: Mapped[UUID] = mapped_column(ForeignKey('identidades_infraestructura.id'), unique=True)
    cluster_id: Mapped[str] = mapped_column(String(80))
    perfil_id: Mapped[str] = mapped_column(String(64))
    perfil_revision: Mapped[int] = mapped_column(Integer)
    slot_id: Mapped[str] = mapped_column(String(64))
    address: Mapped[str] = mapped_column(String(45))
    mac: Mapped[str] = mapped_column(String(17))
    host: Mapped[str] = mapped_column(String(253))
    snapshot: Mapped[dict] = mapped_column(JSON)
    creada_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    liberada_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
