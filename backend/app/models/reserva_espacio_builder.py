from datetime import datetime
from uuid import UUID
from sqlalchemy import DateTime,ForeignKey,String,BigInteger,CheckConstraint,Index
from sqlalchemy.orm import Mapped,mapped_column
from app.database import Base
from app.models.cierre_base import UUIDPrimaryKey,utc_now


class ReservaEspacioBuilder(UUIDPrimaryKey,Base):
    __tablename__='reservas_espacio_builder'
    __table_args__=(CheckConstraint('bytes_temporales >= 0 AND bytes_finales_previstos >= 0',name='ck_reserva_builder_bytes'),Index('ix_reserva_builder_scope','scope_id','estado'))
    ensayo_id: Mapped[UUID]=mapped_column(ForeignKey('ensayos_preparacion.id'),unique=True)
    host_id: Mapped[str]=mapped_column(String(100))
    scope_id: Mapped[str]=mapped_column(ForeignKey('presupuestos_builder.scope_id'))
    bytes_temporales: Mapped[int]=mapped_column(BigInteger)
    bytes_finales_previstos: Mapped[int]=mapped_column(BigInteger)
    estado: Mapped[str]=mapped_column(String(30),default='reservado')
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utc_now)
    liberado_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
