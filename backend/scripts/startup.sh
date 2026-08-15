#!/bin/bash
set -e

echo "🚀 Iniciando aplicación..."

# Esperar a que la base de datos esté lista
echo "⏳ Esperando base de datos..."
python -m scripts.wait_for_db

# Ejecutar migraciones
echo "📊 Ejecutando migraciones..."
alembic upgrade head

# Crear usuario admin
echo "👤 Creando usuario admin..."
python -m scripts.seed_admin

# Crear usuario de cátedra y otros datos de desarrollo
echo "👥 Creando datos de desarrollo..."
python -m scripts.seed_dev

echo "✅ Startup completado"

# Iniciar la aplicación
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
