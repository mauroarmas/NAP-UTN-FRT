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

        # Verificar que existe al menos una cátedra, si no, crear una por defecto
        result = await session.execute(select(Catedra))
        catedra = result.scalars().first()
        if not catedra:
            catedra = Catedra(
                nombre="Cátedra de Prueba",
                descripcion="Cátedra creada automáticamente por el seed de desarrollo",
                cuota_vcpus=4,
                cuota_ram_mb=4096,
                cuota_storage_gb=40,
                activa=True,
            )
            session.add(catedra)
            await session.commit()
            await session.refresh(catedra)
            print(f"✅ Cátedra creada: [{catedra.id}] {catedra.nombre}")
        else:
            print(f"✅ Usando cátedra: [{catedra.id}] {catedra.nombre}")

        # Crear usuario cátedra si no existe
        result = await session.execute(
            select(Usuario).where(Usuario.username == "catedra")
        )
        if result.scalar_one_or_none():
            print("⚠️  El usuario 'catedra' ya existe.")
        else:
            catedra_user = Usuario(
                username="catedra",
                email="catedra@utn.frt.edu.ar",
                nombre="Usuario Cátedra",
                password_hash=get_password_hash("catedra"),
                rol=RolUsuario.CATEDRA_ADMIN,
                catedra_id=catedra.id,
                activo=True,
            )
            session.add(catedra_user)
            await session.commit()
            print("✅ Usuario cátedra creado:")
            print(f"   Username : catedra")
            print(f"   Password : catedra")
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
        print("   admin / admin         → Administrador")
        print("   catedra / catedra     → Cátedra (puede crear pedidos)")


if __name__ == "__main__":
    asyncio.run(seed())
