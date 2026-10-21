#!/bin/bash
set -e

echo "🚀 Iniciando aplicación..."

# Esperar a que la base de datos esté lista
echo "⏳ Esperando base de datos..."
python -m scripts.wait_for_db

# Migración y bootstrap son intervenciones explícitas previas al despliegue.
# Reiniciar nunca cambia cuentas, esquema o catálogo.
echo "✅ Base disponible; iniciando API sin seeds ni migraciones automáticas"

# Iniciar la aplicación
if [ "${APP_RELOAD:-false}" = "true" ]; then
  echo "🔄 Modo desarrollo: recarga automática activada"
  exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir /app/app
else
  exec uvicorn app.main:app --host 0.0.0.0 --port 8000
fi
