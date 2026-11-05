from datetime import datetime
from uuid import UUID
from sqlalchemy import DateTime,ForeignKey,String,Integer,JSON,UniqueConstraint,event
from sqlalchemy.orm import Mapped,mapped_column
from app.database import Base
from app.models.cierre_base import UUIDPrimaryKey,utc_now


class PublicacionOferta(UUIDPrimaryKey,Base):
    __tablename__='publicaciones_oferta'
    __table_args__=(UniqueConstraint('template_id','revision',name='uq_publicacion_revision'),)
    template_id: Mapped[int]=mapped_column(ForeignKey('recurso_templates.id'))
    definicion_id: Mapped[UUID]=mapped_column(ForeignKey('definiciones_servicio.id'))
    ensayo_id: Mapped[UUID]=mapped_column(ForeignKey('ensayos_preparacion.id'))
    revision: Mapped[int]=mapped_column(Integer)
    snapshot: Mapped[dict]=mapped_column(JSON)
    creado_por: Mapped[int]=mapped_column(ForeignKey('usuarios.id'))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utc_now)


@event.listens_for(PublicacionOferta,'before_update')
@event.listens_for(PublicacionOferta,'before_delete')
def preserve(*args):raise ValueError('La publicación histórica no se altera')
