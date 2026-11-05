from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, Text, JSON, CheckConstraint, UniqueConstraint, Index, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.cierre_base import UUIDPrimaryKey, utc_now


class SesionAutenticacion(UUIDPrimaryKey, Base):
    __tablename__ = 'sesiones_autenticacion'
    usuario_id: Mapped[int] = mapped_column(ForeignKey('usuarios.id'), index=True)
    proposito: Mapped[str] = mapped_column(String(20))
    auth_version: Mapped[int]
    creada_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expira_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mfa_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (CheckConstraint("proposito IN ('mfa_pending','onboarding','recovery','operativo')", name='ck_sesion_proposito'),)


class DesafioAutenticacion(UUIDPrimaryKey, Base):
    __tablename__ = 'desafios_autenticacion'
    usuario_id: Mapped[int] = mapped_column(ForeignKey('usuarios.id'), index=True)
    sesion_id: Mapped[UUID | None] = mapped_column(ForeignKey('sesiones_autenticacion.id'), index=True)
    tipo: Mapped[str] = mapped_column(String(30))
    token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    secreto_pendiente_cifrado: Mapped[str | None] = mapped_column(Text)
    creado_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expira_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumido_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revocado_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    intentos: Mapped[int] = mapped_column(default=0, server_default='0')
    actor_institucional: Mapped[str | None] = mapped_column(String(200))
    motivo: Mapped[str | None] = mapped_column(String(500))
    referencia: Mapped[str | None] = mapped_column(String(200))
    __table_args__ = (
        CheckConstraint("tipo IN ('login_totp','enrollment','replacement','assisted_recovery')", name='ck_desafio_tipo'),
        CheckConstraint("sesion_id IS NOT NULL OR tipo = 'assisted_recovery'", name='ck_desafio_sesion'),
        Index('uq_desafio_pendiente_tipo', 'usuario_id', 'tipo', unique=True,
              postgresql_where=text("consumido_at IS NULL AND revocado_at IS NULL AND tipo <> 'login_totp'"),
              sqlite_where=text("consumido_at IS NULL AND revocado_at IS NULL AND tipo <> 'login_totp'")),
    )


class CodigoRecuperacion(UUIDPrimaryKey, Base):
    __tablename__ = 'codigos_recuperacion'
    usuario_id: Mapped[int] = mapped_column(ForeignKey('usuarios.id'), index=True)
    generacion: Mapped[int]
    codigo_hash: Mapped[str] = mapped_column(String(64))
    creado_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    consumido_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invalidado_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint('usuario_id', 'generacion', 'codigo_hash', name='uq_codigo_generacion_hash'),)


class IntentoAutenticacion(Base):
    __tablename__ = 'intentos_autenticacion'
    clase: Mapped[str] = mapped_column(String(10), primary_key=True)
    clave: Mapped[str] = mapped_column(String(64), primary_key=True)
    fallos_recientes: Mapped[list] = mapped_column(JSON, default=list)
    bloqueado_hasta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    __table_args__ = (CheckConstraint("clase IN ('cuenta','origen')", name='ck_intento_clase'),)
