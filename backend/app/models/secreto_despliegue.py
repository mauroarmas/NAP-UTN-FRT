from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.cierre_base import UUIDPrimaryKey, utc_now


class SecretoDespliegue(UUIDPrimaryKey, Base):
    __tablename__ = 'secretos_despliegue'
    __table_args__ = (
        UniqueConstraint('pedido_id', 'nombre', 'revision', name='uq_secreto_pedido_nombre_revision'),
        CheckConstraint('revision > 0', name='ck_secreto_revision'),
        CheckConstraint("origen IN ('generado','aportado')", name='ck_secreto_origen'),
        CheckConstraint('length(nombre) BETWEEN 1 AND 64 AND length(valor_cifrado) > 0', name='ck_secreto_contenido'),
    )
    pedido_id: Mapped[int] = mapped_column(ForeignKey('pedidos.id'), index=True)
    configuracion_id: Mapped[UUID] = mapped_column(ForeignKey('configuraciones_despliegue.id'))
    nombre: Mapped[str] = mapped_column(String(64))
    revision: Mapped[int] = mapped_column(Integer)
    origen: Mapped[str] = mapped_column(String(12))
    valor_cifrado: Mapped[str] = mapped_column(Text)
    creado_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
