"""
Seed: crea datos de prueba para el entorno de desarrollo.

Crea un usuario de cátedra y le asigna la titularidad de una cátedra.

La relación se invirtió: antes el usuario apuntaba a su (única) cátedra, ahora
la cátedra apunta a su titular. Por eso hay que crear la persona primero y
después colgarle la cátedra, no al revés.

Uso:
    cd backend
    ./venv/bin/python scripts/seed_dev.py
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
        # --- Usuario de cátedra ---
        result = await session.execute(
            select(Usuario).where(Usuario.username == "catedra")
        )
        catedra_user = result.scalar_one_or_none()

        if catedra_user:
            print("⚠️  El usuario 'catedra' ya existe.")
        else:
            catedra_user = Usuario(
                username="catedra",
                email="catedra@utn.frt.edu.ar",
                nombre="Usuario Cátedra",
                password_hash=get_password_hash("catedra"),
                rol=RolUsuario.CATEDRA_ADMIN,
                activo=True,
            )
            session.add(catedra_user)
            await session.commit()
            await session.refresh(catedra_user)
            print("✅ Usuario cátedra creado (catedra / catedra)")

        # --- Cátedra a su nombre ---
        result = await session.execute(
            select(Catedra).where(Catedra.titular_id == catedra_user.id)
        )
        propia = result.scalars().first()

        if propia:
            print(f"✅ Ya es titular de: [{propia.id}] {propia.nombre}")
        else:
            # Se reutiliza una cátedra sin responsable si la hay; si no, se crea.
            result = await session.execute(
                select(Catedra).where(Catedra.titular_id.is_(None))
            )
            libre = result.scalars().first()

            if libre:
                libre.titular_id = catedra_user.id
                await session.commit()
                print(f"✅ Cátedra [{libre.id}] {libre.nombre} asignada a 'catedra'")
            else:
                nueva = Catedra(
                    nombre="Cátedra de Prueba",
                    descripcion="Creada automáticamente por el seed de desarrollo",
                    titular_id=catedra_user.id,
                    activa=True,
                )
                session.add(nueva)
                await session.commit()
                await session.refresh(nueva)
                print(f"✅ Cátedra creada: [{nueva.id}] {nueva.nombre}")

        # El administrador no necesita cátedras: su alcance es el sistema entero.
        result = await session.execute(
            select(Usuario).where(Usuario.username == "admin")
        )
        if result.scalar_one_or_none():
            print("✅ Administrador presente (no requiere cátedra asignada)")

        print("\n🎉 Seed completado. Podés iniciar sesión con:")
        print("   admin / admin         → Administrador")
        print("   catedra / catedra     → Cátedra (puede crear pedidos)")


if __name__ == "__main__":
    asyncio.run(seed())
