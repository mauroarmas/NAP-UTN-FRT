#!/bin/bash

# Script para gestionar Docker Compose del proyecto

set -e

COMMAND="${1:-up}"

case "$COMMAND" in
  up)
    echo "🚀 Levantando todos los servicios..."
    docker compose up
    ;;
  down)
    echo "🛑 Deteniendo todos los servicios..."
    docker compose down
    ;;
  build)
    echo "🔨 Construyendo imágenes..."
    docker compose build
    ;;
  rebuild)
    echo "🔨 Reconstruyendo imágenes sin caché..."
    docker compose build --no-cache
    ;;
  logs)
    echo "📋 Mostrando logs..."
    docker compose logs -f
    ;;
  logs-api)
    echo "📋 Logs del backend..."
    docker compose logs -f api
    ;;
  logs-db)
    echo "📋 Logs de la base de datos..."
    docker compose logs -f db
    ;;
  logs-frontend)
    echo "📋 Logs del frontend..."
    docker compose logs -f frontend
    ;;
  shell-api)
    echo "🐚 Accediendo al backend..."
    docker compose exec api bash
    ;;
  shell-db)
    echo "🐚 Accediendo a la base de datos..."
    docker compose exec db psql -U ps_user -d ps_db
    ;;
  clean)
    echo "🧹 Limpiando contenedores, volúmenes e imágenes..."
    docker compose down -v --remove-orphans
    ;;
  help)
    echo "Uso: ./docker-dev.sh [comando]"
    echo ""
    echo "Comandos disponibles:"
    echo "  up           - Levanta todos los servicios (default)"
    echo "  down         - Detiene todos los servicios"
    echo "  build        - Construye las imágenes Docker"
    echo "  rebuild      - Reconstruye sin caché"
    echo "  logs         - Muestra logs de todos los servicios"
    echo "  logs-api     - Logs solo del backend"
    echo "  logs-db      - Logs solo de la BD"
    echo "  logs-frontend - Logs solo del frontend"
    echo "  shell-api    - Acceso shell al backend"
    echo "  shell-db     - Acceso a psql"
    echo "  clean        - Limpia todo (contenedores, volúmenes, imágenes)"
    echo "  help         - Muestra esta ayuda"
    ;;
  *)
    echo "❌ Comando desconocido: $COMMAND"
    echo "Ejecuta './docker-dev.sh help' para ver opciones"
    exit 1
    ;;
esac
