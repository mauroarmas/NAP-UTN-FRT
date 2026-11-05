from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint, event, inspect
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.cierre_base import UUIDPrimaryKey, utc_now


class ConfiguracionDespliegue(UUIDPrimaryKey, Base):
    __tablename__ = 'configuraciones_despliegue'
    __table_args__ = (
        UniqueConstraint('codigo', 'revision', name='uq_configuracion_codigo_revision'),
        CheckConstraint('revision > 0 AND perfil_revision > 0', name='ck_configuracion_revisiones'),
        CheckConstraint("origen IN ('imagen_docker','community_scripts')", name='ck_configuracion_origen'),
        CheckConstraint("modelo_servicio IN ('paas','saas')", name='ck_configuracion_modelo'),
        CheckConstraint("estado IN ('validada','retirada')", name='ck_configuracion_estado'),
        CheckConstraint("(estado = 'validada' AND retirada_at IS NULL) OR (estado = 'retirada' AND retirada_at IS NOT NULL)", name='ck_configuracion_retirada'),
        CheckConstraint('length(sha256) = 64 AND length(perfil_sha256) = 64', name='ck_configuracion_hashes'),
    )
    codigo: Mapped[str] = mapped_column(String(100))
    revision: Mapped[int] = mapped_column(Integer)
    origen: Mapped[str] = mapped_column(String(30))
    modelo_servicio: Mapped[str] = mapped_column(String(10))
    documento: Mapped[dict] = mapped_column(JSON)
    sha256: Mapped[str] = mapped_column(String(64))
    perfil_id: Mapped[str] = mapped_column(String(64))
    perfil_revision: Mapped[int] = mapped_column(Integer)
    perfil_sha256: Mapped[str] = mapped_column(String(64))
    estado: Mapped[str] = mapped_column(String(20), default='validada', server_default='validada')
    validaciones: Mapped[dict] = mapped_column(JSON)
    creado_por: Mapped[int] = mapped_column(ForeignKey('usuarios.id'))
    creado_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    retirada_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


@event.listens_for(ConfiguracionDespliegue, 'before_insert')
def coherent_configuration(mapper, connection, row):
    from app.schemas.configuracion_despliegue import validar_documento, digest_configuracion
    document = validar_documento(row.documento)
    if (document != row.documento or digest_configuracion(document) != row.sha256
            or document['origen'] != row.origen or document['modelo_servicio'] != row.modelo_servicio
            or document['perfil'] != {'id': row.perfil_id, 'revision': row.perfil_revision, 'sha256': row.perfil_sha256}):
        raise ValueError('La configuración y su identidad no coinciden')


@event.listens_for(ConfiguracionDespliegue, 'before_update')
def immutable_configuration(mapper, connection, row):
    state = inspect(row)
    if any(state.attrs[f.key].history.has_changes() for f in mapper.column_attrs if f.key not in {'estado', 'retirada_at'}):
        raise ValueError('Una configuración validada es inmutable')
    history = state.attrs.estado.history
    previous = history.deleted[0] if history.deleted else row.estado
    if ((history.has_changes() and (previous, row.estado) != ('validada', 'retirada'))
            or state.attrs.retirada_at.history.has_changes() and (previous != 'validada' or row.estado != 'retirada')):
        raise ValueError('La retirada de una configuración es definitiva')


@event.listens_for(ConfiguracionDespliegue, 'before_delete')
def preserve_configuration(*args):
    raise ValueError('Las configuraciones se retiran; no se borran')
