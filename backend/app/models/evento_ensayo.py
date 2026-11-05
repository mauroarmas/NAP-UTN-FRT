from datetime import datetime
from uuid import UUID
from sqlalchemy import DateTime,ForeignKey,JSON,String,Text,UniqueConstraint,event
from sqlalchemy.orm import Mapped,mapped_column
from app.database import Base
from app.models.cierre_base import UUIDPrimaryKey,utc_now


class EventoEnsayo(UUIDPrimaryKey,Base):
    __tablename__='eventos_ensayo'
    __table_args__=(UniqueConstraint('ensayo_id','evento_clave',name='uq_evento_ensayo_clave'),)
    ensayo_id: Mapped[UUID]=mapped_column(ForeignKey('ensayos_preparacion.id'))
    operacion_id: Mapped[UUID|None]=mapped_column(ForeignKey('operaciones_ensayo.id'))
    evento_clave: Mapped[str]=mapped_column(String(200))
    anterior: Mapped[str|None]=mapped_column(String(40))
    nuevo: Mapped[str]=mapped_column(String(40))
    actor_tipo: Mapped[str]=mapped_column(String(20))
    actor_id: Mapped[str]=mapped_column(String(100))
    motivo: Mapped[str|None]=mapped_column(Text)
    metadata_segura: Mapped[dict]=mapped_column(JSON,default=dict)
    creado_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utc_now)


@event.listens_for(EventoEnsayo,'before_update')
@event.listens_for(EventoEnsayo,'before_delete')
def preserve(*args):raise ValueError('El historial de ensayo es de sólo agregado')
