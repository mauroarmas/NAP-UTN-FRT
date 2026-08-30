from datetime import datetime

from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MigracionAccesoPerdido(Base):
    """Bitácora de quiénes perdieron acceso al pasar a titular único.

    El modelo anterior admitía varias personas por cátedra; el nuevo exige una
    sola titular. La migración elige de forma determinista (el ``id`` más bajo)
    y deja acá constancia del resto.

    No es un registro de error: es el requisito. Lo inaceptable no es que
    alguien quede afuera —eso es consecuencia de la decisión de titular único—,
    sino que se entere al no poder entrar.
    """

    __tablename__ = "migracion_004_accesos_perdidos"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    # Copias literales: la bitácora tiene que seguir siendo legible aunque
    # después se borre el usuario o se renombre la cátedra.
    username: Mapped[str] = mapped_column(String(50), nullable=False)
    catedra_id: Mapped[int] = mapped_column(ForeignKey("catedras.id"), nullable=False)
    catedra_nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    migrado_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<AccesoPerdido {self.username} → {self.catedra_nombre}>"
