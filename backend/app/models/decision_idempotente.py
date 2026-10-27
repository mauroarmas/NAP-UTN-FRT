from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, JSON, String, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.cierre_base import UUIDPrimaryKey, utc_now


class DecisionIdempotente(UUIDPrimaryKey, Base):
    __tablename__ = 'decisiones_idempotentes'
    __table_args__ = (
        UniqueConstraint('actor_tipo', 'actor_id_normalizado', 'idempotency_key', name='uq_decision_actor_clave'),
        CheckConstraint("actor_tipo IN ('usuario','sistema')"),
    )
    actor_tipo: Mapped[str] = mapped_column(String(10), default='usuario')
    actor_id_normalizado: Mapped[str] = mapped_column(String(80))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    metodo: Mapped[str] = mapped_column(String(10))
    ruta_canonica: Mapped[str] = mapped_column(String(300))
    target_tipo: Mapped[str | None] = mapped_column(String(40))
    target_id: Mapped[str | None] = mapped_column(String(80))
    request_hash: Mapped[str] = mapped_column(String(64))
    response_status: Mapped[int] = mapped_column(Integer)
    resultado_referencia: Mapped[dict] = mapped_column(JSON)
    creado_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
