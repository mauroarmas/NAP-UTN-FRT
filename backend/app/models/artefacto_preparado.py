from datetime import datetime
from uuid import UUID
from sqlalchemy import DateTime,ForeignKey,JSON,String,BigInteger,UniqueConstraint
from sqlalchemy.orm import Mapped,mapped_column
from app.database import Base
from app.models.cierre_base import UUIDPrimaryKey,utc_now


class ArtefactoPreparado(UUIDPrimaryKey,Base):
    __tablename__='artefactos_preparados'
    definicion_id: Mapped[UUID]=mapped_column(ForeignKey('definiciones_servicio.id'),unique=True)
    entradas_sha256: Mapped[str]=mapped_column(String(64))
    estado: Mapped[str]=mapped_column(String(30),default='construyendo')
    registro_id: Mapped[str]=mapped_column(String(100))
    scope_id: Mapped[str]=mapped_column(ForeignKey('presupuestos_builder.scope_id'))
    volume_id: Mapped[str]=mapped_column(String(240))
    image_sha256: Mapped[str]=mapped_column(String(64))
    image_bytes: Mapped[int]=mapped_column(BigInteger)
    bundle_sha256: Mapped[str]=mapped_column(String(64))
    bundle_bytes: Mapped[int]=mapped_column(BigInteger)
    manifest: Mapped[dict]=mapped_column(JSON,default=dict)
    saneamiento: Mapped[dict]=mapped_column(JSON,default=dict)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utc_now)


class ReplicaArtefacto(UUIDPrimaryKey,Base):
    __tablename__='replicas_artefacto'
    __table_args__=(UniqueConstraint('artefacto_id','nodo','storage_id',name='uq_replica_destino'),)
    artefacto_id: Mapped[UUID]=mapped_column(ForeignKey('artefactos_preparados.id'))
    nodo: Mapped[str]=mapped_column(String(100))
    storage_id: Mapped[str]=mapped_column(String(100))
    image_sha256: Mapped[str]=mapped_column(String(64))
    bundle_sha256: Mapped[str]=mapped_column(String(64))
    registro_revision: Mapped[str]=mapped_column(String(100))
    verified_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utc_now)


from sqlalchemy import event, inspect, select


@event.listens_for(ArtefactoPreparado,'before_update')
def immutable_approved_artifact(mapper,connection,target):
    from app.models.definicion_servicio import DefinicionServicio
    state=connection.execute(select(DefinicionServicio.estado).where(DefinicionServicio.id==target.definicion_id)).scalar_one()
    if state!='borrador' and any(inspect(target).attrs[field].history.has_changes() for field in [
        'definicion_id','entradas_sha256','registro_id','scope_id','volume_id','image_sha256','image_bytes','bundle_sha256','bundle_bytes','manifest','saneamiento']):
        raise ValueError('El artefacto de una versión validada es inmutable')


@event.listens_for(ArtefactoPreparado,'before_delete')
def preserve_artifact(*args):raise ValueError('Conservar artefactos e historia de preparación')
