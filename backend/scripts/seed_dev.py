"""Datos mínimos de desarrollo, sin cuentas ni servicios ficticiamente publicados."""
import asyncio
from sqlalchemy import select
from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models.catedra import Catedra

async def seed():
    if get_settings().app_env != 'development':
        raise ValueError('Seed exclusivo de desarrollo')
    async with AsyncSessionLocal() as db, db.begin():
        exists = await db.scalar(select(Catedra.id).where(Catedra.nombre == 'Cátedra de Prueba').limit(1))
        if not exists:
            db.add(Catedra(nombre='Cátedra de Prueba', descripcion='Datos locales de desarrollo', activa=True))
    print('Cátedra de desarrollo preparada. Crear administración con bootstrap_admin y publicar definiciones verificadas.')

if __name__ == '__main__':
    asyncio.run(seed())
