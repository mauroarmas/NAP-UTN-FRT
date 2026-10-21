from datetime import datetime
from sqlalchemy import String, Text, DateTime, ForeignKey, JSON, UniqueConstraint, CheckConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models.cierre_base import UUIDPrimaryKey, utc_now


class Notificacion(UUIDPrimaryKey, Base):
    __tablename__ = 'notificaciones'
    evento_clave: Mapped[str] = mapped_column(String(200))
    destinatario_usuario_id: Mapped[int | None] = mapped_column(ForeignKey('usuarios.id'))
    destinatario_normalizado: Mapped[str] = mapped_column(String(200))
    destinatario_email_cifrado: Mapped[str | None] = mapped_column(Text)
    canal: Mapped[str] = mapped_column(String(10))
    catedra_id: Mapped[int | None] = mapped_column(ForeignKey('catedras.id'))
    servicio_id: Mapped[int | None] = mapped_column(ForeignKey('servicios.id'))
    estado: Mapped[str] = mapped_column(String(20), default='pendiente', server_default='pendiente')
    payload: Mapped[dict] = mapped_column(JSON)
    secreto_temporal_encrypted: Mapped[str | None] = mapped_column(Text)
    secreto_expira_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    auth_version_objetivo: Mapped[int | None]
    intentos: Mapped[int] = mapped_column(default=0, server_default='0')
    proximo_intento_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    ultimo_error: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    enviada_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_owner: Mapped[str | None] = mapped_column(String(36))
    lease_hasta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    generation: Mapped[int] = mapped_column(default=0, server_default='0')
    __table_args__ = (
        UniqueConstraint('evento_clave', 'destinatario_normalizado', 'canal', name='uq_notificacion_evento_destino'),
        CheckConstraint("estado IN ('pendiente','enviando','enviada','fallida','cancelada')", name='ck_notificacion_estado'),
        CheckConstraint("canal IN ('portal','email')", name='ck_notificacion_canal'),
        Index('ix_notificacion_pendiente_fecha', 'estado', 'proximo_intento_at'),
    )
