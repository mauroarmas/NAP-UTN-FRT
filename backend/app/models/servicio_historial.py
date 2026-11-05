from uuid import UUID
from sqlalchemy import Uuid, UniqueConstraint
from datetime import datetime

from sqlalchemy import String, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ServicioHistorial(Base):
    """Rastro de lo que le fue pasando a un servicio.

    Existe por separado del historial de pedidos porque un servicio puede no
    tener pedido detrás (``Servicio.pedido_id`` es nullable) y porque su ciclo
    de vida —encendido, apagado, pausa, vencimiento, renovación— es más largo
    que el del pedido que lo originó.

    Es de solo agregado: no se sobrescribe ni se borra.
    """

    __tablename__ = "servicios_historial"

    __table_args__ = (UniqueConstraint('servicio_id', 'evento_clave', name='uq_historial_servicio_evento'),)

    id: Mapped[int] = mapped_column(primary_key=True)
    servicio_id: Mapped[int] = mapped_column(
        ForeignKey("servicios.id"), nullable=False
    )
    estado_anterior: Mapped[str] = mapped_column(String(20), nullable=False)
    estado_nuevo: Mapped[str] = mapped_column(String(20), nullable=False)
    # El motivo en lenguaje llano: "sin uso desde 2026-08-01", "vencido".
    comentario: Mapped[str | None] = mapped_column(Text, nullable=True)
    # NULL = lo ejecutó el sistema, no una persona.
    usuario_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    operacion_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey('operaciones_infraestructura.id'))
    evento_clave: Mapped[str | None] = mapped_column(String(200))
    actor_tipo: Mapped[str | None] = mapped_column(String(10))
    decision_metadata: Mapped[dict | None] = mapped_column(JSON)

    # Relaciones
    servicio: Mapped["Servicio"] = relationship(back_populates="historial")

    def __repr__(self) -> str:
        return f"<ServicioHistorial {self.estado_anterior} → {self.estado_nuevo}>"
