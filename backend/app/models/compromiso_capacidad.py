from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.cierre_base import UUIDPrimaryKey, utc_now


class CompromisoCapacidad(UUIDPrimaryKey, Base):
    __tablename__ = 'compromisos_capacidad'
    __table_args__ = (
        CheckConstraint('vcpus_retenidos >= 0 AND ram_mb_retenida >= 0 AND disk_bytes_retenidos >= 0'),
        CheckConstraint("estado IN ('reservado','materializado','incierto','liberado')"),
        CheckConstraint("estado != 'liberado' OR (vcpus_retenidos = 0 AND ram_mb_retenida = 0 AND disk_bytes_retenidos = 0 AND liberado_at IS NOT NULL)"),
        Index('uq_compromiso_alta_abierto', 'pedido_id', unique=True,
              postgresql_where=text('liberado_at IS NULL'), sqlite_where=text('liberado_at IS NULL')),
        Index('uq_compromiso_servicio_abierto', 'servicio_id', unique=True,
              postgresql_where=text('liberado_at IS NULL'), sqlite_where=text('liberado_at IS NULL')),
        Index('uq_compromiso_identidad_abierto', 'identidad_infraestructura_id', unique=True,
              postgresql_where=text('liberado_at IS NULL'), sqlite_where=text('liberado_at IS NULL')),
        Index('ix_compromiso_destino', 'estado', 'nodo', 'storage_scope'),
    )
    pedido_id: Mapped[int] = mapped_column(ForeignKey('pedidos.id'))
    servicio_id: Mapped[int | None] = mapped_column(ForeignKey('servicios.id'))
    identidad_infraestructura_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey('identidades_infraestructura.id'))
    nodo: Mapped[str] = mapped_column(String(100))
    storage_id: Mapped[str] = mapped_column(String(100))
    storage_scope: Mapped[str] = mapped_column(String(200))
    vcpus_retenidos: Mapped[int] = mapped_column(Integer, default=0)
    ram_mb_retenida: Mapped[int] = mapped_column(BigInteger, default=0)
    disk_bytes_retenidos: Mapped[int] = mapped_column(BigInteger, default=0)
    estado: Mapped[str] = mapped_column(String(20), default='reservado')
    revision: Mapped[int] = mapped_column(Integer, default=1)
    creado_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expira_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    liberado_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    justificacion_sobreasignacion: Mapped[str | None] = mapped_column(Text)
