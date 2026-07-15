from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.database import Base


class RolUsuario(str, enum.Enum):
    ADMIN = "admin"
    CATEDRA_ADMIN = "catedra_admin"


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    totp_secret: Mapped[str | None] = mapped_column(String(32), nullable=True)
    totp_habilitado: Mapped[bool] = mapped_column(Boolean, default=False)
    rol: Mapped[RolUsuario] = mapped_column(
        SAEnum(RolUsuario), default=RolUsuario.CATEDRA_ADMIN
    )
    catedra_id: Mapped[int | None] = mapped_column(
        ForeignKey("catedras.id"), nullable=True
    )
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relaciones
    catedra: Mapped["Catedra | None"] = relationship(back_populates="usuarios")
    pedidos: Mapped[list["Pedido"]] = relationship(back_populates="solicitante")

    def __repr__(self) -> str:
        return f"<Usuario {self.username} ({self.rol.value})>"
