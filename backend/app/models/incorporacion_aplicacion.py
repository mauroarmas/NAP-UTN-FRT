from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, UniqueConstraint, Integer, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models.cierre_base import UUIDPrimaryKey, utc_now


class IncorporacionAplicacion(UUIDPrimaryKey, Base):
    __tablename__ = 'incorporaciones_aplicacion'
    __table_args__ = (UniqueConstraint('proveedor','identidad_externa','origen_clave',name='uq_incorporacion_origen'),
        CheckConstraint('revision >= 1', name='ck_incorporacion_revision'))
    proveedor: Mapped[str] = mapped_column(String(40), default='community-scripts')
    identidad_externa: Mapped[str] = mapped_column(String(180))
    origen_clave: Mapped[str] = mapped_column(String(180))
    revision_fuente: Mapped[str] = mapped_column(String(40))
    comando_sha256: Mapped[str] = mapped_column(String(64))
    comando_origen: Mapped[str] = mapped_column(Text)
    url_origen: Mapped[str] = mapped_column(Text)
    version_externa: Mapped[str | None] = mapped_column(String(100))
    nombre: Mapped[str] = mapped_column(String(150))
    descripcion: Mapped[str | None] = mapped_column(Text)
    categorias: Mapped[list] = mapped_column(JSON, default=list)
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    datos_origen: Mapped[dict] = mapped_column(JSON, default=dict)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    creado_por: Mapped[int] = mapped_column(ForeignKey('usuarios.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
