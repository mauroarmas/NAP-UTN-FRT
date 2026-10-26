from datetime import datetime
from uuid import UUID
from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped,mapped_column
from app.database import Base
from app.models.cierre_base import UUIDPrimaryKey


class RecursoEnsayo(UUIDPrimaryKey,Base):
    __tablename__='recursos_ensayo'
    __table_args__=(UniqueConstraint('ensayo_id','rol',name='uq_recurso_ensayo_rol'),)
    ensayo_id: Mapped[UUID]=mapped_column(ForeignKey('ensayos_preparacion.id'))
    rol: Mapped[str]=mapped_column(String(30))
    identidad_infraestructura_id: Mapped[UUID|None]=mapped_column(ForeignKey('identidades_infraestructura.id',use_alter=True,name='fk_recurso_ensayo_identidad'),unique=True)
    destino_snapshot: Mapped[dict]=mapped_column(JSON,default=dict)
    acceso_metadata: Mapped[dict]=mapped_column(JSON,default=dict)
    credenciales_encrypted: Mapped[str|None]=mapped_column(Text)
    ausencia_confirmada_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
