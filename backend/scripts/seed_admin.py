"""Script para crear el usuario administrador inicial."""
import asyncio
import sys
import os

# Agregar el directorio padre al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from app.database import AsyncSessionLocal, engine, Base
from app.models.usuario import Usuario, RolUsuario
from app.utils.security import get_password_hash


async def create_admin():
    async with AsyncSessionLocal() as session:
        # Verificar si ya existe un admin.
        # `first()` y no `scalar_one_or_none()`: la pregunta es "¿hay alguno?",
        # y el portal permite crear más de un administrador. Exigir que haya
        # exactamente uno hacía que el arranque abortara con
        # MultipleResultsFound en cuanto existía un segundo admin, dejando el
        # backend en bucle de reinicio (startup.sh corre con `set -e`).
        result = await session.execute(
            select(Usuario).where(Usuario.rol == RolUsuario.ADMIN).limit(1)
        )
        existing = result.scalars().first()

        if existing:
            print(f"⚠️  Ya existe un administrador: {existing.username}")
            return

        admin = Usuario(
            username="admin",
            email="admin@utn.frt.edu.ar",
            nombre="Administrador",
            password_hash=get_password_hash("admin"),
            rol=RolUsuario.ADMIN,
            activo=True,
        )

        session.add(admin)
        await session.commit()
        print("✅ Usuario administrador creado:")
        print(f"   Username: admin")
        print(f"   Password: admin")
        print(f"   Rol: admin")
        print(f"   ⚠️  Cambiá la contraseña en producción!")


if __name__ == "__main__":
    asyncio.run(create_admin())
