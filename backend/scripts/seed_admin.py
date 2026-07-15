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
        # Verificar si ya existe un admin
        result = await session.execute(
            select(Usuario).where(Usuario.rol == RolUsuario.ADMIN)
        )
        existing = result.scalar_one_or_none()

        if existing:
            print(f"⚠️  Ya existe un administrador: {existing.username}")
            return

        admin = Usuario(
            username="admin",
            email="admin@utn.frt.edu.ar",
            nombre="Administrador",
            password_hash=get_password_hash("admin123"),
            rol=RolUsuario.ADMIN,
            activo=True,
        )

        session.add(admin)
        await session.commit()
        print("✅ Usuario administrador creado:")
        print(f"   Username: admin")
        print(f"   Password: admin123")
        print(f"   Rol: admin")
        print(f"   ⚠️  Cambiá la contraseña en producción!")


if __name__ == "__main__":
    asyncio.run(create_admin())
