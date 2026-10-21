from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, JSON, String, UniqueConstraint, Uuid, event, inspect
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.cierre_base import UUIDPrimaryKey, utc_now


class DefinicionServicio(UUIDPrimaryKey, Base):
    __tablename__ = 'definiciones_servicio'
    __table_args__ = (
        UniqueConstraint('codigo', 'version', name='uq_definicion_codigo_version'),
        CheckConstraint("estado IN ('borrador','validada','publicada','retirada')"),
        CheckConstraint("tipo_recurso = 'lxc'"),
        CheckConstraint("modelo_servicio IN ('iaas','paas','saas')"),
    )
    codigo: Mapped[str] = mapped_column(String(100))
    version: Mapped[str] = mapped_column(String(80))
    modelo_servicio: Mapped[str] = mapped_column(String(10))
    tipo_recurso: Mapped[str] = mapped_column(String(10), default='lxc')
    producto: Mapped[str] = mapped_column(String(40))
    manifest: Mapped[dict] = mapped_column(JSON, default=dict)
    manifest_sha256: Mapped[str | None] = mapped_column(String(64))
    estado: Mapped[str] = mapped_column(String(20), default='borrador')
    validada_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    validada_por: Mapped[int | None] = mapped_column(ForeignKey('usuarios.id'))
    evidencia_validacion: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey('evidencias.id'))
    retirada_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


@event.listens_for(DefinicionServicio, 'before_update')
def immutable_validated_definition(mapper, connection, target):
    state = inspect(target)
    history = state.attrs.estado.history
    previous = history.deleted[0] if history.deleted else target.estado
    if previous != 'borrador':
        immutable = ['codigo', 'version', 'modelo_servicio', 'tipo_recurso', 'producto', 'manifest',
            'manifest_sha256', 'validada_at', 'validada_por', 'evidencia_validacion']
        if any(state.attrs[field].history.has_changes() for field in immutable):
            raise ValueError('El contenido de una versión validada es inmutable')
    if history.has_changes() and target.estado not in {
        'borrador': {'validada'}, 'validada': {'publicada', 'retirada'}, 'publicada': {'retirada'}, 'retirada': set(),
    }.get(previous, set()):
        raise ValueError('Transición de definición inválida')


@event.listens_for(DefinicionServicio, 'before_delete')
def preserve_definition(*args):
    raise ValueError('Las definiciones se retiran; no se borran')
