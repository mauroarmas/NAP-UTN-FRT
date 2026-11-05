from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.cierre_base import utc_now

ESTADOS_IDENTIDAD = ('en_preparacion', 'lista', 'con_error', 'retirada')


class IdentidadConsola(Base):
    """Identidad individual de consola de una persona, gestionada por el portal (feature 022).

    La contraseña sólo existe cifrada y nunca se expone; el conjunto *deseado* de pools no se guarda: se calcula.
    """
    __tablename__ = 'identidades_consola'
    __table_args__ = (
        CheckConstraint("estado IN ('en_preparacion','lista','con_error','retirada')", name='ck_identidad_consola_estado'),
        CheckConstraint("identidad ~ '^nap-u[0-9]+@pve$'", name='ck_identidad_consola_nombre'),
        CheckConstraint('revision >= 1', name='ck_identidad_consola_revision'),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey('usuarios.id'), unique=True)
    identidad: Mapped[str] = mapped_column(String(100), unique=True)
    password_cifrada: Mapped[str] = mapped_column(Text)
    estado: Mapped[str] = mapped_column(String(20), default='en_preparacion', server_default='en_preparacion')
    pools_aplicados: Mapped[list] = mapped_column(JSON, default=list, server_default=text("'[]'"))
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default='1')
    ultimo_error_seguro: Mapped[str | None] = mapped_column(String(200))
    reconciliada_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    creada_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    actualizada_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
