from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid, JSON, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.cierre_base import UUIDPrimaryKey, utc_now


class OperacionInfraestructura(UUIDPrimaryKey, Base):
    __tablename__ = 'operaciones_infraestructura'
    __table_args__ = (
        CheckConstraint("tipo IN ('desplegar','iniciar','detener','reiniciar','pausar','eliminar','reparar')"),
        CheckConstraint("estado IN ('pendiente','en_curso','confirmada','fallida','incierta')"),
        CheckConstraint("actor_tipo IN ('usuario','sistema')"),
        UniqueConstraint('actor_tipo', 'actor_id_normalizado', 'idempotency_key', name='uq_operacion_actor_clave'),
        *[Index('uq_operacion_abierta_' + field, field, unique=True,
                postgresql_where=text("estado IN ('pendiente','en_curso','incierta')"),
                sqlite_where=text("estado IN ('pendiente','en_curso','incierta')"))
          for field in ['pedido_id', 'servicio_id', 'identidad_infraestructura_id']],
        Index('ix_operacion_poll', 'estado', 'next_poll_at'),
    )
    tipo: Mapped[str] = mapped_column(String(20))
    operacion_raiz_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey('operaciones_infraestructura.id', name='fk_operacion_raiz'), index=True)
    pedido_id: Mapped[int | None] = mapped_column(ForeignKey('pedidos.id'))
    servicio_id: Mapped[int | None] = mapped_column(ForeignKey('servicios.id'))
    identidad_infraestructura_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey('identidades_infraestructura.id'))
    actor_usuario_id: Mapped[int | None] = mapped_column(ForeignKey('usuarios.id'))
    actor_tipo: Mapped[str] = mapped_column(String(10), default='usuario')
    actor_id_normalizado: Mapped[str] = mapped_column(String(80))
    motivo: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    estado: Mapped[str] = mapped_column(String(20), default='pendiente')
    fase: Mapped[str] = mapped_column(String(40), default='preparacion')
    upid: Mapped[str | None] = mapped_column(String(300))
    intento: Mapped[int] = mapped_column(Integer, default=0)
    error_codigo: Mapped[str | None] = mapped_column(String(80))
    error_detalle_seguro: Mapped[str | None] = mapped_column(Text)
    creado_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    confirmada_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_poll_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    lease_owner: Mapped[UUID | None] = mapped_column(Uuid)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_generation: Mapped[int] = mapped_column(Integer, default=0)
    contexto_seguro: Mapped[dict] = mapped_column(JSON, default=dict, server_default='{}')
    dispatch_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
