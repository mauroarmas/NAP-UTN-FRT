from sqlalchemy import String, Integer, Boolean, Text, JSON, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.database import Base


class TipoRecurso(str, enum.Enum):
    LXC = "lxc"
    QEMU = "qemu"


class RecursoTemplate(Base):
    __tablename__ = "recurso_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    tipo: Mapped[TipoRecurso] = mapped_column(
        SAEnum(TipoRecurso), default=TipoRecurso.LXC
    )
    default_vcpus: Mapped[int] = mapped_column(Integer, default=1)
    default_ram_mb: Mapped[int] = mapped_column(Integer, default=256)
    default_disk_gb: Mapped[int] = mapped_column(Integer, default=2)
    os_template: Mapped[str | None] = mapped_column(String(200), nullable=True)
    config_extra: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relaciones
    pedidos: Mapped[list["Pedido"]] = relationship(back_populates="template")
    servicios: Mapped[list["Servicio"]] = relationship(back_populates="template")

    def __repr__(self) -> str:
        return f"<RecursoTemplate {self.nombre} ({self.tipo.value})>"
