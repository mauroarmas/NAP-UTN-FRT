from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.cierre_base import UUIDPrimaryKey, utc_now


class IntentoDespliegue(UUIDPrimaryKey, Base):
    __tablename__ = 'intentos_despliegue'
    __table_args__ = (
        UniqueConstraint('operacion_raiz_id', 'numero', name='uq_intento_raiz_numero'),
        UniqueConstraint('operacion_raiz_id', 'id', 'execution_id', name='uq_intento_identidad_consola'),
        CheckConstraint('numero > 0 AND ultimo_source_seq >= 0', name='ck_intento_contadores'),
        CheckConstraint("estado IN ('preparado','ejecutando','confirmado','fallido','incierto')", name='ck_intento_estado'),
        CheckConstraint('length(configuracion_sha256) = 64', name='ck_intento_hash'),
    )
    operacion_id: Mapped[UUID] = mapped_column(ForeignKey('operaciones_infraestructura.id'), unique=True)
    operacion_raiz_id: Mapped[UUID] = mapped_column(ForeignKey('operaciones_infraestructura.id'), index=True)
    numero: Mapped[int] = mapped_column(Integer)
    execution_id: Mapped[UUID] = mapped_column(Uuid, unique=True, default=uuid4)
    identidad_infraestructura_id: Mapped[UUID] = mapped_column(ForeignKey('identidades_infraestructura.id'))
    configuracion_sha256: Mapped[str] = mapped_column(String(64))
    estado: Mapped[str] = mapped_column(String(20), default='preparado', server_default='preparado')
    runner_job_id: Mapped[str | None] = mapped_column(String(100))
    node_boot_id: Mapped[UUID | None] = mapped_column(Uuid)
    creado_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    iniciado_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observado_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    terminado_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ultimo_source_seq: Mapped[int] = mapped_column(BigInteger, default=0, server_default='0')
    error_codigo: Mapped[str | None] = mapped_column(String(80))
    error_detalle_seguro: Mapped[str | None] = mapped_column(String(500))
