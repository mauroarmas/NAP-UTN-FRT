from datetime import datetime

from sqlalchemy import String, Integer, DateTime, ForeignKey, Text, JSON, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.database import Base


class EstadoPedido(str, enum.Enum):
    SOLICITADO = "solicitado"
    EN_REVISION = "en_revision"
    APROBADO = "aprobado"
    EN_DESPLIEGUE = "en_despliegue"
    ACTIVO = "activo"
    RECHAZADO = "rechazado"
    ERROR = "error"
    SUSPENDIDO = "suspendido"


class Pedido(Base):
    __tablename__ = "pedidos"

    id: Mapped[int] = mapped_column(primary_key=True)
    catedra_id: Mapped[int] = mapped_column(ForeignKey("catedras.id"), nullable=False)
    solicitante_id: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id"), nullable=False
    )
    template_id: Mapped[int] = mapped_column(
        ForeignKey("recurso_templates.id"), nullable=False
    )
    estado: Mapped[EstadoPedido] = mapped_column(
        SAEnum(EstadoPedido), default=EstadoPedido.SOLICITADO
    )
    motivo_rechazo: Mapped[str | None] = mapped_column(Text, nullable=True)
    parametros_extra: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relaciones
    catedra: Mapped["Catedra"] = relationship(back_populates="pedidos")
    solicitante: Mapped["Usuario"] = relationship(back_populates="pedidos")
    template: Mapped["RecursoTemplate"] = relationship(back_populates="pedidos")
    historial: Mapped[list["PedidoHistorial"]] = relationship(
        back_populates="pedido", order_by="PedidoHistorial.created_at"
    )
    servicio: Mapped["Servicio | None"] = relationship(back_populates="pedido")

    def __repr__(self) -> str:
        return f"<Pedido #{self.id} ({self.estado.value})>"


class PedidoHistorial(Base):
    __tablename__ = "pedidos_historial"

    id: Mapped[int] = mapped_column(primary_key=True)
    pedido_id: Mapped[int] = mapped_column(ForeignKey("pedidos.id"), nullable=False)
    estado_anterior: Mapped[str] = mapped_column(String(20), nullable=False)
    estado_nuevo: Mapped[str] = mapped_column(String(20), nullable=False)
    comentario: Mapped[str | None] = mapped_column(Text, nullable=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relaciones
    pedido: Mapped["Pedido"] = relationship(back_populates="historial")

    def __repr__(self) -> str:
        return f"<PedidoHistorial {self.estado_anterior} → {self.estado_nuevo}>"
