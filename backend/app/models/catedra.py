from datetime import datetime

from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Catedra(Base):
    __tablename__ = "catedras"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    cuota_vcpus: Mapped[int] = mapped_column(Integer, default=2)
    cuota_ram_mb: Mapped[int] = mapped_column(Integer, default=1024)
    cuota_storage_gb: Mapped[int] = mapped_column(Integer, default=8)
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relaciones
    usuarios: Mapped[list["Usuario"]] = relationship(back_populates="catedra")
    pedidos: Mapped[list["Pedido"]] = relationship(back_populates="catedra")
    servicios: Mapped[list["Servicio"]] = relationship(back_populates="catedra")

    def __repr__(self) -> str:
        return f"<Catedra {self.nombre}>"
