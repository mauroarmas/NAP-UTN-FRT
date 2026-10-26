from datetime import datetime
from uuid import UUID
from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, Integer, CheckConstraint, UniqueConstraint, Index,text
from sqlalchemy.orm import Mapped,mapped_column
from app.database import Base
from app.models.cierre_base import UUIDPrimaryKey,utc_now


class OperacionEnsayo(UUIDPrimaryKey,Base):
    __tablename__='operaciones_ensayo'
    __table_args__=(UniqueConstraint('ensayo_id','idempotency_key',name='uq_operacion_ensayo_clave'),
        CheckConstraint("estado IN ('pendiente','en_curso','confirmada','fallida','incierta')",name='ck_operacion_ensayo_estado'),
        Index('uq_operacion_ensayo_recurso_abierta','recurso_id',unique=True,postgresql_where=text("estado IN ('pendiente','en_curso','incierta')"),sqlite_where=text("estado IN ('pendiente','en_curso','incierta')")),
        Index('uq_operacion_ensayo_builder_abierta','ensayo_id',unique=True,postgresql_where=text("recurso_id IS NULL AND estado IN ('pendiente','en_curso','incierta')"),sqlite_where=text("recurso_id IS NULL AND estado IN ('pendiente','en_curso','incierta')")))
    ensayo_id: Mapped[UUID]=mapped_column(ForeignKey('ensayos_preparacion.id'))
    recurso_id: Mapped[UUID|None]=mapped_column(ForeignKey('recursos_ensayo.id'))
    tipo: Mapped[str]=mapped_column(String(40))
    fase: Mapped[str]=mapped_column(String(60),default='pendiente')
    estado: Mapped[str]=mapped_column(String(20),default='pendiente')
    actor_tipo: Mapped[str]=mapped_column(String(20),default='usuario')
    actor_id: Mapped[str]=mapped_column(String(100))
    idempotency_key: Mapped[str]=mapped_column(String(128))
    request_hash: Mapped[str|None]=mapped_column(String(64))
    job_id: Mapped[str|None]=mapped_column(String(200))
    upid: Mapped[str|None]=mapped_column(String(300))
    contexto_seguro: Mapped[dict]=mapped_column(JSON,default=dict)
    resultado: Mapped[dict]=mapped_column(JSON,default=dict)
    intento: Mapped[int]=mapped_column(Integer,default=0)
    lease_generation: Mapped[int]=mapped_column(Integer,default=0)
    lease_owner: Mapped[str|None]=mapped_column(String(100))
    lease_until: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    dispatch_started_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    deadline_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    next_poll_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utc_now)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utc_now)
    error_codigo: Mapped[str|None]=mapped_column(String(100))
