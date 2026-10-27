from datetime import datetime
from sqlalchemy import DateTime,String,BigInteger,Integer,Boolean,CheckConstraint
from sqlalchemy.orm import Mapped,mapped_column
from app.database import Base
from app.models.cierre_base import utc_now


class PresupuestoBuilder(Base):
    __tablename__='presupuestos_builder'
    __table_args__=(CheckConstraint('limite_bytes > 0 AND revision_config >= 1',name='ck_presupuesto_builder_positivo'),)
    scope_id: Mapped[str]=mapped_column(String(100),primary_key=True)
    revision_config: Mapped[int]=mapped_column(Integer)
    limite_bytes: Mapped[int]=mapped_column(BigInteger)
    habilitado: Mapped[bool]=mapped_column(Boolean,default=True)
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utc_now)
