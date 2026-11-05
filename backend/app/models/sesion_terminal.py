from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.cierre_base import utc_now

MOTIVOS_CIERRE = ('inactividad', 'persona', 'retiro', 'baja', 'detencion', 'cuenta', 'administracion',
                  'reinicio_portal', 'error', 'limite')


class SesionTerminal(Base):
    """Una terminal abierta por una persona sobre un servicio (feature 022). No guarda NUNCA contenido."""
    __tablename__ = 'sesiones_terminal'
    __table_args__ = (
        CheckConstraint("motivo_cierre IS NULL OR motivo_cierre IN ('inactividad','persona','retiro','baja','detencion',"
                        "'cuenta','administracion','reinicio_portal','error','limite')", name='ck_sesion_terminal_motivo'),
        Index('ix_sesiones_terminal_usuario', 'usuario_id', 'cerrada_at'),
        Index('ix_sesiones_terminal_servicio', 'servicio_id', 'cerrada_at'),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    usuario_id: Mapped[int] = mapped_column(ForeignKey('usuarios.id'))
    servicio_id: Mapped[int] = mapped_column(ForeignKey('servicios.id'))
    nodo: Mapped[str] = mapped_column(String(64))
    abierta_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    ultimo_latido_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    ultima_entrada_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    cierre_solicitado_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    motivo_solicitud: Mapped[str | None] = mapped_column(String(32))
    cerrada_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    motivo_cierre: Mapped[str | None] = mapped_column(String(32))
    duracion_s: Mapped[int | None] = mapped_column(Integer)
