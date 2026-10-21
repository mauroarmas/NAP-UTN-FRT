from uuid import UUID
from sqlalchemy import String, Integer, Boolean, Text, JSON, ForeignKey, Uuid, CheckConstraint, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.database import Base
from app.models.pedido import ModeloServicio


class TipoRecurso(str, enum.Enum):
    LXC = "lxc"
    QEMU = "qemu"


class RecursoTemplate(Base):
    __tablename__ = "recurso_templates"
    __table_args__ = (CheckConstraint('default_vcpus > 0 AND default_ram_mb > 0 AND default_disk_gb > 0',name='ck_template_recursos_positivos'),)

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    modelo_servicio: Mapped[ModeloServicio] = mapped_column(
        SAEnum(
            ModeloServicio,
            name="modeloservicio",
            values_callable=lambda obj: [e.value for e in obj],
            native_enum=False,
        ),
        default=ModeloServicio.IAAS,
        nullable=False,
    )
    tipo: Mapped[TipoRecurso] = mapped_column(
        SAEnum(TipoRecurso), default=TipoRecurso.LXC
    )
    default_vcpus: Mapped[int] = mapped_column(Integer, default=1)
    default_ram_mb: Mapped[int] = mapped_column(Integer, default=256)
    default_disk_gb: Mapped[int] = mapped_column(Integer, default=2)
    justificacion_disco: Mapped[str | None] = mapped_column(Text, nullable=True)
    os_template: Mapped[str | None] = mapped_column(String(200), nullable=True)
    config_extra: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default='1')
    definicion_version_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey('definiciones_servicio.id'), index=True)

    # Relaciones
    pedidos: Mapped[list["Pedido"]] = relationship(back_populates="template")
    servicios: Mapped[list["Servicio"]] = relationship(back_populates="template")

    def __repr__(self) -> str:
        return f"<RecursoTemplate {self.nombre} ({self.tipo.value})>"
