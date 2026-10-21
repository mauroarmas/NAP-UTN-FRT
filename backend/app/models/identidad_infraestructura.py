from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.cierre_base import UUIDPrimaryKey, utc_now


class IdentidadInfraestructura(UUIDPrimaryKey, Base):
    __tablename__ = 'identidades_infraestructura'
    __table_args__ = (
        CheckConstraint('vmid > 0'),
        CheckConstraint("estado IN ('reclamada','materializada','incierta','retirada')"),
        Index('uq_identidad_vmid_retenido', 'cluster_id', 'vmid', unique=True,
              postgresql_where=text('ausencia_confirmada_at IS NULL'), sqlite_where=text('ausencia_confirmada_at IS NULL')),
    )
    cluster_id: Mapped[str] = mapped_column(String(80))
    vmid: Mapped[int] = mapped_column(Integer)
    nodo: Mapped[str] = mapped_column(String(100))
    pool_catedra: Mapped[str] = mapped_column(String(100))
    resource_uuid: Mapped[UUID] = mapped_column(Uuid, unique=True, default=uuid4)
    nonce_cifrado: Mapped[str] = mapped_column(Text)
    definition_sha256: Mapped[str | None] = mapped_column(String(64))
    bundle_sha256: Mapped[str | None] = mapped_column(String(64))
    pedido_alta_id: Mapped[int | None] = mapped_column(ForeignKey('pedidos.id'))
    servicio_id: Mapped[int | None] = mapped_column(ForeignKey('servicios.id'))
    estado: Mapped[str] = mapped_column(String(20), default='reclamada')
    claimed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    ausencia_confirmada_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ownership_verificada_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
