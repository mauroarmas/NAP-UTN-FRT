# Docker Setup - Guía Rápida

## ⚡ Comando Rápido

Para levantar **todo el proyecto** (Backend + Database + Frontend) con un solo comando:

```bash
docker compose up
```

Eso es todo. El proyecto estará disponible en:
- 🌐 Frontend: http://localhost:5173
- 🔌 API: http://localhost:8000
- 🐘 Database: localhost:5432

## 📦 Con el Script Auxiliar

Si prefieres un script más amigable con más opciones:

```bash
# Levantar todo
./docker-dev.sh up

# Detener
./docker-dev.sh down

# Ver logs
./docker-dev.sh logs

# Ver logs solo del backend
./docker-dev.sh logs-api

# Acceso shell al backend
./docker-dev.sh shell-api

# Limpiar todo
./docker-dev.sh clean

# Ver todas las opciones
./docker-dev.sh help
```

## 🔧 Requisitos

- Docker
- Docker Compose v2 (incluido en versiones modernas de Docker Desktop)

## 📋 Servicios

El proyecto incluye 3 servicios que se levantan automáticamente:

| Servicio | Puerto | Tecnología | Descripción |
|----------|--------|-----------|-------------|
| **db** | 5432 | PostgreSQL 16 | Base de datos |
| **api** | 8000 | Python/FastAPI | Backend |
| **frontend** | 5173 | Node/Vite | Frontend |

## 🔐 Credenciales por Defecto

- **DB User**: `ps_user`
- **DB Password**: `ps_password`
- **DB Name**: `ps_db`

Para variables de Proxmox, configúralas en el archivo `.env`:
```bash
PROXMOX_HOST=192.168.1.92
PROXMOX_TOKEN_NAME=ps-dev
PROXMOX_TOKEN_VALUE=tu-token-aqui
```

## 🗂️ Estructura de Archivos

```
.
├── docker-compose.yml    # Configuración de servicios
├── dockerfile            # Imagen del backend
├── frontend.dockerfile   # Imagen del frontend
├── docker-dev.sh         # Script auxiliar
├── backend/              # Código del backend
├── frontend/             # Código del frontend
└── .env                  # Variables de entorno
```

## 🧹 Limpiar Todo

Si necesitas limpiar contenedores, volúmenes e imágenes:

```bash
docker compose down -v --remove-orphans
```

O usa el script:

```bash
./docker-dev.sh clean
```

## 🚀 Desarrollo

Para desarrollo con hot-reload del frontend, puedes modificar el `docker-compose.yml` para usar `npm run dev` en lugar de `serve`. La configuración actual está optimizada para producción.
