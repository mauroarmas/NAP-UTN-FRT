from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, JSON, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.cierre_base import utc_now


class ConsolaOperacion(Base):
    __tablename__ = 'consolas_operacion'
    __table_args__ = (
        CheckConstraint('next_seq > 0 AND first_retained_seq > 0 AND last_seq >= 0 AND next_seq = last_seq + 1 AND first_retained_seq <= next_seq', name='ck_consola_secuencia'),
        CheckConstraint('retained_bytes BETWEEN 0 AND 10000000 AND dropped_bytes >= 0 AND dropped_messages >= 0', name='ck_consola_cuota'),
    )
    operacion_raiz_id: Mapped[UUID] = mapped_column(ForeignKey('operaciones_infraestructura.id'), primary_key=True)
    next_seq: Mapped[int] = mapped_column(BigInteger, default=1, server_default='1')
    first_retained_seq: Mapped[int] = mapped_column(BigInteger, default=1, server_default='1')
    last_seq: Mapped[int] = mapped_column(BigInteger, default=0, server_default='0')
    retained_bytes: Mapped[int] = mapped_column(BigInteger, default=0, server_default='0')
    dropped_bytes: Mapped[int] = mapped_column(BigInteger, default=0, server_default='0')
    dropped_messages: Mapped[int] = mapped_column(BigInteger, default=0, server_default='0')
    last_captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    truncated: Mapped[bool] = mapped_column(Boolean, default=False, server_default='false')
    expired: Mapped[bool] = mapped_column(Boolean, default=False, server_default='false')
    ultimo_resultado_seguro: Mapped[dict | None] = mapped_column(JSON)


class ConsolaFragmento(Base):
    __tablename__ = 'consola_fragmentos'
    __table_args__ = (
        UniqueConstraint('execution_id', 'source', 'source_key', name='uq_consola_evento_productor'),
        ForeignKeyConstraint(['operacion_raiz_id', 'intento_id', 'execution_id'],
            ['intentos_despliegue.operacion_raiz_id', 'intentos_despliegue.id', 'intentos_despliegue.execution_id'], name='fk_consola_intento_identidad'),
        CheckConstraint("(source = 'runner' AND source_seq IS NOT NULL AND source_seq > 0 AND source_key = CAST(source_seq AS VARCHAR)) OR (source = 'portal' AND source_seq IS NULL AND stream = 'sistema')", name='ck_consola_productor'),
        CheckConstraint("stream IN ('sistema','stdout','stderr')", name='ck_consola_stream'),
        CheckConstraint('seq > 0 AND utf8_bytes BETWEEN 1 AND 8192', name='ck_consola_fragmento_limite'),
        CheckConstraint('octet_length(texto_depurado) = utf8_bytes', name='ck_consola_utf8').ddl_if(dialect='postgresql'),
        Index('ix_consola_captura', 'captured_at'),
    )
    operacion_raiz_id: Mapped[UUID] = mapped_column(ForeignKey('consolas_operacion.operacion_raiz_id'), primary_key=True)
    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    intento_id: Mapped[UUID] = mapped_column(Uuid)
    execution_id: Mapped[UUID] = mapped_column(Uuid)
    source: Mapped[str] = mapped_column(String(10))
    source_key: Mapped[str] = mapped_column(String(160))
    source_seq: Mapped[int | None] = mapped_column(BigInteger)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    fase: Mapped[str] = mapped_column(String(40))
    stream: Mapped[str] = mapped_column(String(10))
    texto_depurado: Mapped[str] = mapped_column(Text)
    utf8_bytes: Mapped[int] = mapped_column(Integer)
