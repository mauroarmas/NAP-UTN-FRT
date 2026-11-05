from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Float, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.utils.clock import clock


class MetricaSnapshot(Base):
    __tablename__ = "metricas_snapshots"
    __table_args__ = (
        UniqueConstraint('servicio_id', 'intervalo_at', name='uq_metrica_servicio_minuto'),
        Index('ix_metrica_servicio_fecha', 'servicio_id', 'timestamp'),
        CheckConstraint("calidad IN ('confirmada','no_confirmada')", name='ck_metrica_calidad'),
        CheckConstraint('net_in_bytes IS NULL OR net_in_bytes >= 0', name='ck_metrica_net_in'),
        CheckConstraint('net_out_bytes IS NULL OR net_out_bytes >= 0', name='ck_metrica_net_out'),
        CheckConstraint('net_in_delta IS NULL OR net_in_delta >= 0', name='ck_metrica_delta_in'),
        CheckConstraint('net_out_delta IS NULL OR net_out_delta >= 0', name='ck_metrica_delta_out'),
        CheckConstraint('duracion_observada_s >= 0 AND duracion_observada_s <= 120', name='ck_metrica_duracion'),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    servicio_id: Mapped[int] = mapped_column(
        ForeignKey("servicios.id"), nullable=False
    )
    cpu_usage_percent: Mapped[float | None] = mapped_column(Float)
    ram_usage_mb: Mapped[float | None] = mapped_column(Float)
    disk_usage_gb: Mapped[float | None] = mapped_column(Float)
    net_in_bytes: Mapped[int | None] = mapped_column(BigInteger)
    net_out_bytes: Mapped[int | None] = mapped_column(BigInteger)
    # Bytes Float históricos conservados; no restauran bits perdidos por redondeo.
    net_in_legacy: Mapped[float | None] = mapped_column(Float)
    net_out_legacy: Mapped[float | None] = mapped_column(Float)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: clock.now())
    intervalo_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    calidad: Mapped[str] = mapped_column(String(20), default='no_confirmada', server_default='no_confirmada')
    estado_observado: Mapped[str | None] = mapped_column(String(20))
    aplicacion_saludable: Mapped[bool | None] = mapped_column(Boolean)
    uptime_s: Mapped[int | None] = mapped_column(BigInteger)
    epoca_contador: Mapped[str | None] = mapped_column(String(64))
    ram_max_mb: Mapped[float | None] = mapped_column(Float)
    disk_max_bytes: Mapped[int | None] = mapped_column(BigInteger)
    vcpus_observadas: Mapped[int | None] = mapped_column(Integer)
    net_in_delta: Mapped[int | None] = mapped_column(BigInteger)
    net_out_delta: Mapped[int | None] = mapped_column(BigInteger)
    duracion_observada_s: Mapped[int] = mapped_column(Integer, default=0, server_default='0')

    # Relaciones
    servicio: Mapped["Servicio"] = relationship(back_populates="metricas")

    def __repr__(self) -> str:
        return f"<MetricaSnapshot servicio={self.servicio_id} @ {self.timestamp}>"
