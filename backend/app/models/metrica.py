from datetime import datetime

from sqlalchemy import Integer, Float, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class MetricaSnapshot(Base):
    __tablename__ = "metricas_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    servicio_id: Mapped[int] = mapped_column(
        ForeignKey("servicios.id"), nullable=False
    )
    cpu_usage_percent: Mapped[float] = mapped_column(Float, default=0.0)
    ram_usage_mb: Mapped[float] = mapped_column(Float, default=0.0)
    disk_usage_gb: Mapped[float] = mapped_column(Float, default=0.0)
    net_in_bytes: Mapped[float] = mapped_column(Float, default=0.0)
    net_out_bytes: Mapped[float] = mapped_column(Float, default=0.0)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relaciones
    servicio: Mapped["Servicio"] = relationship(back_populates="metricas")

    def __repr__(self) -> str:
        return f"<MetricaSnapshot servicio={self.servicio_id} @ {self.timestamp}>"
