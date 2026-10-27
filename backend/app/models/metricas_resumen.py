from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MetricaResumenDiario(Base):
    __tablename__ = 'metricas_resumen_diario'
    __table_args__ = (
        Index('ix_resumen_catedra_fecha', 'catedra_id', 'fecha_local'),
        CheckConstraint('intervalos_validos >= 0 AND intervalos_validos <= intervalos_esperados', name='ck_resumen_cobertura'),
        CheckConstraint('segundos_observados >= 0 AND segundos_running >= 0', name='ck_resumen_segundos'),
    )
    servicio_id: Mapped[int] = mapped_column(ForeignKey('servicios.id'), primary_key=True)
    fecha_local: Mapped[date] = mapped_column(Date, primary_key=True)
    zona_horaria: Mapped[str] = mapped_column(String(64), primary_key=True)
    catedra_id: Mapped[int] = mapped_column(ForeignKey('catedras.id'))
    intervalos_esperados: Mapped[int] = mapped_column(Integer)
    intervalos_validos: Mapped[int] = mapped_column(Integer)
    segundos_observados: Mapped[int] = mapped_column(Integer)
    cpu_integral: Mapped[float] = mapped_column(Float)
    cpu_max: Mapped[float | None] = mapped_column(Float)
    ram_integral_mb_s: Mapped[float] = mapped_column(Float)
    ram_max_mb: Mapped[float | None] = mapped_column(Float)
    disk_max_bytes: Mapped[int | None] = mapped_column(BigInteger)
    trafico_in_bytes: Mapped[Decimal] = mapped_column(Numeric(30, 0))
    trafico_out_bytes: Mapped[Decimal] = mapped_column(Numeric(30, 0))
    segundos_running: Mapped[int] = mapped_column(Integer)
    # NULL conserva la incertidumbre cuando falta historia de asignación.
    vcpu_segundos: Mapped[int | None] = mapped_column(BigInteger)
    ram_asignada_mb_segundos: Mapped[int | None] = mapped_column(BigInteger)
    disk_asignado_byte_segundos: Mapped[Decimal | None] = mapped_column(Numeric(30, 0))
    periodo_cerrado: Mapped[bool] = mapped_column(Boolean, default=False, server_default='false')
    agregado_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    detalle_purgado_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
