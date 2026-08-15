"""Espera a que PostgreSQL esté listo antes de continuar."""
import asyncio
import sys
import os
from sqlalchemy import text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import AsyncSessionLocal


async def wait_for_db(max_retries=30, delay=1):
    for attempt in range(max_retries):
        try:
            async with AsyncSessionLocal() as session:
                await session.execute(text("SELECT 1"))
            print("✅ Base de datos lista")
            return True
        except Exception as e:
            attempt_num = attempt + 1
            if attempt_num < max_retries:
                print(f"⏳ Intento {attempt_num}/{max_retries}: {e}")
                await asyncio.sleep(delay)
            else:
                print(f"❌ No se pudo conectar a la BD después de {max_retries} intentos")
                return False
    return False


if __name__ == "__main__":
    success = asyncio.run(wait_for_db())
    sys.exit(0 if success else 1)
