from datetime import datetime

from sqlalchemy import String, Integer, DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.database import Base


class EstadoServicio(str, enum.Enum):
    RUNNING = "running"
    STOPPED = "stopped"
    PAUSED = "paused"
    ERROR = "error"


class Servicio(Base):
    __tablename__ = "servicios"

    id: Mapped[int] = mapped_column(primary_key=True)
    catedra_id: Mapped[int] = mapped_column(ForeignKey("catedras.id"), nullable=False)
    pedido_id: Mapped[int | None] = mapped_column(
        ForeignKey("pedidos.id"), unique=True, nullable=True
    )
    template_id: Mapped[int] = mapped_column(
        ForeignKey("recurso_templates.id"), nullable=False
    )
    proxmox_vmid: Mapped[str | None] = mapped_column(String(10), nullable=True)
    proxmox_node: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tipo: Mapped[str] = mapped_column(String(10), default="lxc")
    estado: Mapped[EstadoServicio] = mapped_column(
        SAEnum(EstadoServicio), default=EstadoServicio.STOPPED
    )
    hostname: Mapped[str | None] = mapped_column(String(100), nullable=True)
    vcpus_asignados: Mapped[int] = mapped_column(Integer, default=1)
    ram_asignada_mb: Mapped[int] = mapped_column(Integer, default=256)
    disk_asignado_gb: Mapped[int] = mapped_column(Integer, default=2)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    deployed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relaciones
    catedra: Mapped["Catedra"] = relationship(back_populates="servicios")
    pedido: Mapped["Pedido | None"] = relationship(back_populates="servicio")
    template: Mapped["RecursoTemplate"] = relationship(back_populates="servicios")
    metricas: Mapped[list["MetricaSnapshot"]] = relationship(back_populates="servicio")

    def __repr__(self) -> str:
        return f"<Servicio VMID={self.proxmox_vmid} ({self.estado.value})>"
