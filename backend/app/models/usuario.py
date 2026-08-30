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
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relaciones
    # Una persona puede tener varias cátedras a su cargo; cada cátedra tiene un
    # único titular. La titularidad vive del lado de la cátedra para que los
    # recursos y su historia sobrevivan a un cambio de responsable.
    catedras: Mapped[list["Catedra"]] = relationship(back_populates="titular")
    # `passive_deletes` evita que SQLAlchemy intente anular `solicitante_id` al
    # borrar a la persona: esa columna es NOT NULL porque la autoría de un pedido
    # es parte del historial académico que el Principio V manda conservar. Antes,
    # el intento de anularla terminaba en un 500 sin explicación. Hoy retirar es
    # una baja lógica, pero la declaración queda para que ningún camino futuro
    # vuelva a pelearse con la base.
    pedidos: Mapped[list["Pedido"]] = relationship(
        back_populates="solicitante", passive_deletes=True
    )

    def __repr__(self) -> str:
        return f"<Usuario {self.username} ({self.rol.value})>"
