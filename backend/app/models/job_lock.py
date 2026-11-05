from datetime import datetime

from sqlalchemy import String, DateTime, Uuid
from uuid import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class JobLock(Base):
    """Exclusión mutua para los trabajos periódicos.

    El planificador vive dentro del proceso de la aplicación, así que con más de
    un worker cada trabajo se dispararía una vez por worker: los vencimientos se
    aplicarían N veces. La fila actúa de testigo — quien la inserta, ejecuta.

    Es más simple que introducir una cola externa y alcanza para un despliegue
    de instancia única, que es el caso real de este portal.
    """

    __tablename__ = "job_locks"

    nombre: Mapped[str] = mapped_column(String(50), primary_key=True)
    tomado_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # Identificador del proceso que lo tomó, solo para diagnóstico.
    tomado_por: Mapped[str | None] = mapped_column(String(100), nullable=True)
    owner_token: Mapped[UUID | None] = mapped_column(Uuid)
    generation: Mapped[int] = mapped_column(default=0, server_default='0')
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<JobLock {self.nombre} desde {self.tomado_at}>"
