from datetime import datetime

from sqlalchemy import (
    String,
    Integer,
    DateTime,
    ForeignKey,
    Index,
    Text,
    JSON,
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import text
import enum

from app.database import Base


class EstadoPedido(str, enum.Enum):
    SOLICITADO = "solicitado"
    APROBADO = "aprobado"
    # Transitorio: solo lo asigna el orquestador durante el despliegue real
    # contra Proxmox (ver pedido_service.TRANSICIONES_SISTEMA). Nunca se llega
    # a este estado con un cambio de estado manual.
    EN_DESPLIEGUE = "en_despliegue"
    ACTIVO = "activo"
    RECHAZADO = "rechazado"
    ERROR = "error"
    SUSPENDIDO = "suspendido"


class TipoPedido(str, enum.Enum):
    """Un pedido da de alta un servicio nuevo o renueva uno existente.

    Ambos atraviesan la misma máquina de estados; lo que cambia es el ejecutor
    de la transición a ACTIVO (desplegar un contenedor vs. correr la fecha de
    vencimiento del servicio que ya existe).
    """

    ALTA = "alta"
    RENOVACION = "renovacion"


class Pedido(Base):
    __tablename__ = "pedidos"
    __table_args__ = (
        # Índice parcial: los listados solo consultan filas vigentes.
        Index(
            "ix_pedidos_vigentes",
            "deleted_at",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

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
    tipo: Mapped[TipoPedido] = mapped_column(
        SAEnum(TipoPedido), default=TipoPedido.ALTA, nullable=False
    )
    # Solo en tipo=RENOVACION: el servicio cuya fecha de fin se quiere correr.
    servicio_id: Mapped[int | None] = mapped_column(
        ForeignKey("servicios.id"), nullable=True
    )
    motivo_rechazo: Mapped[str | None] = mapped_column(Text, nullable=True)
    parametros_extra: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # VMID reservado en el clúster antes de intentar crear el contenedor.
    # Se persiste para que un reintento pueda reutilizarlo tras un fallo.
    vmid_reservado: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # --- Reserva de capacidad ---
    # Aprobar no es opinar: compromete capacidad en el acto. Los valores se
    # copian del template al aprobar en lugar de referenciarlo, porque el
    # template puede editarse entre la aprobación y el despliegue y la reserva
    # tiene que ser un compromiso sobre números concretos.
    reserva_vcpus: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reserva_ram_mb: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reserva_disk_gb: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Una reserva que nunca se materializa retendría capacidad para siempre.
    reserva_expira_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Obligatoria cuando se aprueba por encima de la capacidad libre.
    justificacion_capacidad: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relaciones
    catedra: Mapped["Catedra"] = relationship(back_populates="pedidos")
    solicitante: Mapped["Usuario"] = relationship(back_populates="pedidos")
    template: Mapped["RecursoTemplate"] = relationship(back_populates="pedidos")
    historial: Mapped[list["PedidoHistorial"]] = relationship(
        back_populates="pedido", order_by="PedidoHistorial.created_at"
    )
    servicio: Mapped["Servicio | None"] = relationship(
        back_populates="pedido", foreign_keys="Servicio.pedido_id"
    )
    # Solo en renovaciones: el servicio destino.
    servicio_renovado: Mapped["Servicio | None"] = relationship(
        foreign_keys=[servicio_id]
    )

    def __repr__(self) -> str:
        return f"<Pedido #{self.id} ({self.estado.value})>"


class PedidoHistorial(Base):
    __tablename__ = "pedidos_historial"

    id: Mapped[int] = mapped_column(primary_key=True)
    pedido_id: Mapped[int] = mapped_column(ForeignKey("pedidos.id"), nullable=False)
    estado_anterior: Mapped[str] = mapped_column(String(20), nullable=False)
    estado_nuevo: Mapped[str] = mapped_column(String(20), nullable=False)
    comentario: Mapped[str | None] = mapped_column(Text, nullable=True)
    # NULL significa que la transición la ejecutó el propio sistema (expiración
    # de una reserva, vencimiento, pausado automático). No se atribuye a una
    # persona que no la decidió, ni se omite del historial por no tener autor.
    usuario_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relaciones
    pedido: Mapped["Pedido"] = relationship(back_populates="historial")

    def __repr__(self) -> str:
        return f"<PedidoHistorial {self.estado_anterior} → {self.estado_nuevo}>"
