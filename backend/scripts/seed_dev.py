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
        # --- Plantillas iniciales (IaaS, PaaS, SaaS) ---
        from app.models.recurso_template import RecursoTemplate, TipoRecurso
        from app.models.pedido import ModeloServicio

        plantillas_base = [
            {
                "nombre": "Debian 13 LXC small",
                "descripcion": "Contenedor LXC liviano para prácticas estándar",
                "modelo_servicio": ModeloServicio.IAAS,
                "tipo": TipoRecurso.LXC,
                "default_vcpus": 1,
                "default_ram_mb": 512,
                "default_disk_gb": 4,
            },
            {
                "nombre": "Ubuntu server medium",
                "descripcion": "Servidor Linux de propósito general",
                "modelo_servicio": ModeloServicio.IAAS,
                "tipo": TipoRecurso.LXC,
                "default_vcpus": 2,
                "default_ram_mb": 2048,
                "default_disk_gb": 8,
            },
            {
                "nombre": "BookStack (Libro Virtual)",
                "descripcion": "Plataforma de apuntes interactivos y documentación para cátedra",
                "modelo_servicio": ModeloServicio.SAAS,
                "tipo": TipoRecurso.LXC,
                "default_vcpus": 2,
                "default_ram_mb": 2048,
                "default_disk_gb": 10,
            },
            {
                "nombre": "Ollama API (Inferencia LLM)",
                "descripcion": "Endpoint de API local para modelos de lenguaje institucional",
                "modelo_servicio": ModeloServicio.PAAS,
                "tipo": TipoRecurso.LXC,
                "default_vcpus": 4,
                "default_ram_mb": 8192,
                "default_disk_gb": 20,
            },
        ]

        for p_data in plantillas_base:
            t_res = await session.execute(
                select(RecursoTemplate).where(RecursoTemplate.nombre == p_data["nombre"])
            )
            if not t_res.scalar_one_or_none():
                nueva_t = RecursoTemplate(**p_data, activo=True)
                session.add(nueva_t)
                await session.commit()
                print(f"✅ Plantilla creada: [{nueva_t.modelo_servicio.value.upper()}] {nueva_t.nombre}")

        print("\n🎉 Seed completado. Podés iniciar sesión con:")
        print("   admin / admin         → Administrador")
        print("   catedra / catedra     → Cátedra (puede crear pedidos)")


if __name__ == "__main__":
    asyncio.run(seed())
