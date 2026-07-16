"""
Seed: crea datos de prueba para el entorno de desarrollo.
Crea usuario solicitante + lo asigna a la cátedra existente.

Uso:
    cd backend
    source venv/bin/activate
    python scripts/seed_dev.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.usuario import Usuario, RolUsuario
from app.models.catedra import Catedra
from app.utils.security import get_password_hash


async def seed():
    async with AsyncSessionLocal() as session:

        # Verificar que existe al menos una cátedra
        result = await session.execute(select(Catedra))
        catedra = result.scalars().first()
        if not catedra:
            print("⚠️  No hay cátedras. Corré primero el servidor y creá una cátedra desde /catedras.")
            return

        print(f"✅ Usando cátedra: [{catedra.id}] {catedra.nombre}")

        # Crear usuario solicitante si no existe
        result = await session.execute(
            select(Usuario).where(Usuario.username == "solicitante")
        )
        if result.scalar_one_or_none():
            print("⚠️  El usuario 'solicitante' ya existe.")
        else:
            solicitante = Usuario(
                username="solicitante",
                email="solicitante@utn.frt.edu.ar",
                nombre="Juan Pérez",
                password_hash=get_password_hash("solicitante123"),
                rol=RolUsuario.CATEDRA_ADMIN,
                catedra_id=catedra.id,
                activo=True,
            )
            session.add(solicitante)
            await session.commit()
            print("✅ Usuario solicitante creado:")
            print(f"   Username : solicitante")
            print(f"   Password : solicitante123")
            print(f"   Rol      : catedra_admin")
            print(f"   Cátedra  : [{catedra.id}] {catedra.nombre}")

        # Asegurarse de que admin también tiene cátedra asignada
        result = await session.execute(
            select(Usuario).where(Usuario.username == "admin")
        )
        admin = result.scalar_one_or_none()
        if admin and not admin.catedra_id:
            admin.catedra_id = catedra.id
            await session.commit()
            print(f"✅ Admin asignado a cátedra [{catedra.id}]")
        elif admin:
            print(f"✅ Admin ya tiene cátedra [{admin.catedra_id}]")

        print("\n🎉 Seed completado. Podés iniciar sesión con:")
        print("   admin / admin123         → Administrador")
        print("   solicitante / solicitante123  → Cátedra (puede crear pedidos)")


if __name__ == "__main__":
    asyncio.run(seed())
