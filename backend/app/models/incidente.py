from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, JSON, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Incidente(Base):
    __tablename__ = 'incidentes'
    __table_args__ = (
        Index('uq_incidente_abierto', 'servicio_id', 'tipo', unique=True,
            postgresql_where=text("estado = 'abierto'"), sqlite_where=text("estado = 'abierto'")),
        Index('ix_incidente_servicio_fecha', 'servicio_id', 'abierto_at'),
        CheckConstraint("estado IN ('abierto','resuelto')", name='ck_incidente_estado'),
        CheckConstraint("tipo IN ('caida','cpu_sostenida','ram_sostenida','vencimiento_no_aplicado','operacion_incierta')", name='ck_incidente_tipo'),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    servicio_id: Mapped[int] = mapped_column(ForeignKey('servicios.id'))
    tipo: Mapped[str] = mapped_column(String(32))
    estado: Mapped[str] = mapped_column(String(10), default='abierto', server_default='abierto')
    abierto_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ultima_observacion_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resuelto_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    regla_version: Mapped[str] = mapped_column(String(40))
    evidencia: Mapped[dict] = mapped_column(JSON, default=dict)
