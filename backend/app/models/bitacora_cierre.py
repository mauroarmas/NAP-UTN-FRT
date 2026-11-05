from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, JSON, String, Text, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.cierre_base import UUIDPrimaryKey, utc_now


class BitacoraCierre(UUIDPrimaryKey,Base):
    """Registro inmutable de regularización; material legado en cuarentena cifrada."""
    __tablename__='bitacora_cierre'
    __table_args__=(
        UniqueConstraint('entidad_tipo','entidad_id','accion','fuente_sha256',name='uq_cierre_entidad_fuente'),
        CheckConstraint("entidad_tipo IN ('usuario','pedido','servicio')",name='ck_cierre_entidad'),
    )
    entidad_tipo: Mapped[str]=mapped_column(String(20))
    entidad_id: Mapped[str]=mapped_column(String(80))
    fuente_sha256: Mapped[str]=mapped_column(String(64))
    resultado_sha256: Mapped[str]=mapped_column(String(64))
    accion: Mapped[str]=mapped_column(String(40))
    antes_seguro: Mapped[dict]=mapped_column(JSON)
    despues_seguro: Mapped[dict]=mapped_column(JSON)
    pendientes: Mapped[list]=mapped_column(JSON)
    legado_cifrado: Mapped[str|None]=mapped_column(Text)
    actor_institucional: Mapped[str|None]=mapped_column(String(200))
    actor_usuario_id: Mapped[int|None]=mapped_column(ForeignKey('usuarios.id'))
    referencia: Mapped[str]=mapped_column(String(200))
    creado_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utc_now)


@event.listens_for(BitacoraCierre,'before_update')
@event.listens_for(BitacoraCierre,'before_delete')
def preserve_history(*args):
    raise ValueError('La bitácora de cierre es inmutable')
