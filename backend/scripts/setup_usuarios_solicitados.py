"""Configurar usuarios específicos solicitados y restaurar credenciales."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.usuario import Usuario, RolUsuario
from app.models.catedra import Catedra
from app.utils.security import get_password_hash


async def main():
    async with AsyncSessionLocal() as session:
        # 1. Admin solicitado: mauro.armas101@gmail.com
        res = await session.execute(
            select(Usuario).where(
                (Usuario.email == "mauro.armas101@gmail.com")
                | (Usuario.username == "mauro_admin")
                | (Usuario.username == "mauro")
            )
        )
        admin_mauro = res.scalars().first()

        if admin_mauro:
            admin_mauro.username = "mauro_admin"
            admin_mauro.email = "mauro.armas101@gmail.com"
            admin_mauro.nombre = "Mauro Armas (Admin)"
            admin_mauro.password_hash = get_password_hash("Admin123!")
            admin_mauro.rol = RolUsuario.ADMIN
            admin_mauro.activo = True
            admin_mauro.debe_cambiar_password = False
            admin_mauro.recibir_notificaciones_email = True
            print("Updated mauro_admin (mauro.armas101@gmail.com)")
        else:
            admin_mauro = Usuario(
                username="mauro_admin",
                email="mauro.armas101@gmail.com",
                nombre="Mauro Armas (Admin)",
                password_hash=get_password_hash("Admin123!"),
                rol=RolUsuario.ADMIN,
                activo=True,
                debe_cambiar_password=False,
                recibir_notificaciones_email=True,
            )
            session.add(admin_mauro)
            print("Created mauro_admin (mauro.armas101@gmail.com)")

        # 2. Cátedra solicitada: mauro.armas14@gmail.com
        res = await session.execute(
            select(Usuario).where(
                (Usuario.email == "mauro.armas14@gmail.com")
                | (Usuario.username == "mauro_catedra")
            )
        )
        catedra_mauro = res.scalars().first()

        if catedra_mauro:
            catedra_mauro.username = "mauro_catedra"
            catedra_mauro.email = "mauro.armas14@gmail.com"
            catedra_mauro.nombre = "Mauro Armas (Cátedra)"
            catedra_mauro.password_hash = get_password_hash("Docente123!")
            catedra_mauro.rol = RolUsuario.CATEDRA_ADMIN
            catedra_mauro.activo = True
            catedra_mauro.debe_cambiar_password = False
            catedra_mauro.recibir_notificaciones_email = True
            print("Updated mauro_catedra (mauro.armas14@gmail.com)")
        else:
            catedra_mauro = Usuario(
                username="mauro_catedra",
                email="mauro.armas14@gmail.com",
                nombre="Mauro Armas (Cátedra)",
                password_hash=get_password_hash("Docente123!"),
                rol=RolUsuario.CATEDRA_ADMIN,
                activo=True,
                debe_cambiar_password=False,
                recibir_notificaciones_email=True,
            )
            session.add(catedra_mauro)
            print("Created mauro_catedra (mauro.armas14@gmail.com)")

        await session.flush()

        # Asignar cátedras a mauro_catedra
        res_cat = await session.execute(
            select(Catedra).where(Catedra.nombre.in_(["Sistemas Operativos", "Bases de Datos"]))
        )
        cats = res_cat.scalars().all()
        for c in cats:
            c.titular_id = catedra_mauro.id
            print(f"Assigned catedra '{c.nombre}' to mauro_catedra")

        # 3. Asegurar admin por defecto (admin / admin)
        res_admin = await session.execute(
            select(Usuario).where(Usuario.username == "admin")
        )
        default_admin = res_admin.scalars().first()
        if default_admin:
            default_admin.password_hash = get_password_hash("admin")
            default_admin.activo = True
            default_admin.debe_cambiar_password = False
            print("Verified default admin user (admin / admin)")

        # 4. Asegurar catedra por defecto (catedra / catedra)
        res_cat_user = await session.execute(
            select(Usuario).where(Usuario.username == "catedra")
        )
        default_cat = res_cat_user.scalars().first()
        if default_cat:
            default_cat.password_hash = get_password_hash("catedra")
            default_cat.activo = True
            default_cat.debe_cambiar_password = False
            print("Verified default catedra user (catedra / catedra)")

        await session.commit()
        print("All users successfully saved!")


if __name__ == "__main__":
    asyncio.run(main())

