from uuid import UUID
from sqlalchemy import Uuid, UniqueConstraint
from datetime import datetime

from sqlalchemy import (
    String,
    Integer,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    Text,
    Enum as SAEnum,
    CheckConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import text
import enum

from app.database import Base


class EstadoServicio(str, enum.Enum):
    RUNNING = "running"
    STOPPED = "stopped"
    PAUSED = "paused"
    ERROR = "error"


class Servicio(Base):
    __tablename__ = "servicios"
    __table_args__ = (
        CheckConstraint('vcpus_asignados > 0 AND ram_asignada_mb > 0 AND disk_asignado_gb > 0',name='ck_servicio_recursos_positivos'),
        CheckConstraint("modelo_servicio IS NULL OR modelo_servicio IN ('iaas','paas','saas')",name='ck_servicio_modelo'),
        CheckConstraint("disponibilidad_aplicacion IN ('no_verificada','preparando','utilizable','degradada','error')",name='ck_servicio_disponibilidad'),
        # Índice parcial: los listados solo consultan filas vigentes.
        Index(
            "ix_servicios_vigentes",
            "deleted_at",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

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
    url_acceso: Mapped[str | None] = mapped_column(String(255), nullable=True)
    deployed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # --- Vencimiento ---
    # NULL solo en los servicios anteriores a esta feature: un servicio que
    # nunca supo que tenía fecha no se apaga por vencimiento.
    vence_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    aviso_vencimiento_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )

    # --- Pausado por inactividad ---
    # "Siempre encendido": excluye del pausado automático, no del vencimiento.
    exento_pausado: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    # Fin del período de gracia. NULL = no hay pausa programada.
    pausa_programada_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    aviso_pausa_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Marca que distingue "lo pausó el sistema" de "lo apagó la cátedra". Vive
    # en el portal porque Proxmox reporta ambos casos como "stopped".
    pausado_auto_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # No mapeado (sin anotación Mapped, SQLAlchemy lo ignora): marca si el
    # `estado` de esta instancia se confirmó contra Proxmox en la consulta
    # actual. Lo setea `sincronizar_estados` y viaja en ServicioResponse.
    estado_sincronizado = False
    existe_en_proxmox = None

    modelo_servicio: Mapped[str | None] = mapped_column(String(10))
    nombre_snapshot: Mapped[str | None] = mapped_column(String(150))
    definicion_version_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey('definiciones_servicio.id'))
    asignacion_snapshot: Mapped[dict | None] = mapped_column(JSON)
    identidad_infraestructura_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey('identidades_infraestructura.id'), unique=True)
    disponibilidad_aplicacion: Mapped[str] = mapped_column(String(20), default='no_verificada', server_default='no_verificada')
    acceso_metadata: Mapped[dict | None] = mapped_column(JSON)
    credenciales_encrypted: Mapped[str | None] = mapped_column(Text)
    verificado_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observado_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evidencia_acceso_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey('evidencias.id'))
    acceso_red_verificado_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relaciones
    catedra: Mapped["Catedra"] = relationship(back_populates="servicios")
    pedido: Mapped["Pedido | None"] = relationship(
        back_populates="servicio", foreign_keys=[pedido_id]
    )
    historial: Mapped[list["ServicioHistorial"]] = relationship(
        back_populates="servicio", order_by="ServicioHistorial.created_at"
    )
    template: Mapped["RecursoTemplate"] = relationship(back_populates="servicios")
    metricas: Mapped[list["MetricaSnapshot"]] = relationship(back_populates="servicio")

    def __repr__(self) -> str:
        return f"<Servicio VMID={self.proxmox_vmid} ({self.estado.value})>"
