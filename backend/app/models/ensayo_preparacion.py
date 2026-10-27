from datetime import datetime
from uuid import UUID
from sqlalchemy import DateTime, ForeignKey, JSON, String, Integer, Text, Uuid, CheckConstraint, Index, text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models.cierre_base import UUIDPrimaryKey, utc_now


class EnsayoPreparacion(UUIDPrimaryKey, Base):
    __tablename__='ensayos_preparacion'
    __table_args__=(CheckConstraint("estado IN ('pendiente','resolviendo','esperando_confirmacion','construyendo','ensayando','lista_para_comprobar','comprobada','fallida','incierta','descartada','vencida')",name='ck_ensayo_estado'),
        CheckConstraint("limpieza_estado IN ('no_solicitada','pendiente','en_curso','confirmada','fallida')",name='ck_ensayo_limpieza'),
        CheckConstraint('revision >= 1 AND execution_generation >= 1',name='ck_ensayo_revision'),
        Index('uq_ensayo_abierto','definicion_id',unique=True,postgresql_where=text("estado NOT IN ('descartada','vencida','fallida') AND publicacion_id IS NULL"),sqlite_where=text("estado NOT IN ('descartada','vencida','fallida') AND publicacion_id IS NULL")))
    incorporacion_id: Mapped[UUID]=mapped_column(ForeignKey('incorporaciones_aplicacion.id'))
    definicion_id: Mapped[UUID]=mapped_column(ForeignKey('definiciones_servicio.id'))
    perfil_id: Mapped[str]=mapped_column(String(100))
    estado: Mapped[str]=mapped_column(String(40),default='pendiente')
    revision: Mapped[int]=mapped_column(Integer,default=1)
    execution_generation: Mapped[int]=mapped_column(Integer,default=1)
    creado_por: Mapped[int]=mapped_column(ForeignKey('usuarios.id'))
    creado_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utc_now)
    expires_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    aviso_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    avisado_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    cancelada_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    cierre_remoto_confirmado_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    entradas_resueltas: Mapped[dict]=mapped_column(JSON,default=dict)
    entradas_sha256: Mapped[str|None]=mapped_column(String(64))
    confirmada_por: Mapped[int|None]=mapped_column(ForeignKey('usuarios.id'))
    confirmada_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    artefacto_id: Mapped[UUID|None]=mapped_column(ForeignKey('artefactos_preparados.id',use_alter=True,name='fk_ensayo_artefacto'))
    evidencia_id: Mapped[UUID|None]=mapped_column(ForeignKey('evidencias.id'))
    publicacion_id: Mapped[UUID|None]=mapped_column(ForeignKey('publicaciones_oferta.id',use_alter=True,name='fk_ensayo_publicacion'))
    limpieza_estado: Mapped[str]=mapped_column(String(30),default='no_solicitada')
    motivo_cierre: Mapped[str|None]=mapped_column(Text)
    error_codigo: Mapped[str|None]=mapped_column(String(100))
    error_detalle_seguro: Mapped[str|None]=mapped_column(Text)
