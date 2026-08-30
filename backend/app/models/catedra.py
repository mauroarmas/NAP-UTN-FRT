from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Catedra(Base):
    __tablename__ = "catedras"
    __table_args__ = (
        # El nombre dejó de ser único a nivel global: dos personas pueden dictar
        # materias homónimas. Lo que debe ser único es el par nombre + titular.
        UniqueConstraint("titular_id", "nombre", name="uq_catedras_titular_nombre"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Nullable únicamente para permitir la migración por pasos; una cátedra
    # activa con servicios vigentes no puede quedarse sin responsable.
    titular_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id"), nullable=True
    )
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relaciones
    titular: Mapped["Usuario | None"] = relationship(back_populates="catedras")
    pedidos: Mapped[list["Pedido"]] = relationship(back_populates="catedra")
    servicios: Mapped[list["Servicio"]] = relationship(back_populates="catedra")

    def __repr__(self) -> str:
        return f"<Catedra {self.nombre}>"
