# Docker Setup - Guía Rápida

## ⚡ Comando Rápido

Para levantar **todo el proyecto** (Backend + Database + Frontend) con un solo comando:

```bash
docker compose up
```

Eso es todo. El proyecto estará disponible en:
- 🌐 Frontend: http://localhost:5174
- 🔌 API: http://localhost:8001
- 🐘 Database: localhost:5434

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

| Servicio | Puerto (host) | Tecnología | Descripción |
|----------|--------|-----------|-------------|
| **db** | 5434 | PostgreSQL 16 | Base de datos |
| **api** | 8001 | Python/FastAPI | Backend |
| **frontend** | 5174 | Node/Vite | Frontend |

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
├── docker-compose.yml          # Configuración de servicios
├── docker-compose.override.yml # Overrides de desarrollo (recarga automática)
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

## 🚀 Desarrollo con recarga automática

`docker compose up` ya levanta el stack en **modo desarrollo**: no hace falta reiniciar
los contenedores para ver los cambios. Docker Compose carga automáticamente
`docker-compose.override.yml`, que monta el código del host dentro de los contenedores.

| Servicio | Qué corre | Al guardar un archivo |
|----------|-----------|------------------------|
| `api`    | `uvicorn --reload` (vigila `/app/app`) | Reinicia solo el proceso de la app, en ~1s |
| `frontend` | dev server de Vite con HMR | Actualiza el navegador sin recargar la página |

Solo hace falta reconstruir la imagen (`./docker-dev.sh build`) cuando cambian las
**dependencias**: `backend/requirements.txt` o `frontend/package.json`.

### Modo producción

Para levantar con el build estático (sin recarga, frontend servido con `serve`),
hay que ignorar el override:

```bash
./docker-dev.sh prod
# equivalente a: docker compose -f docker-compose.yml up --build
```

### Si el frontend no detecta los cambios

En Linux los eventos de archivo del bind mount funcionan directo. En WSL2, macOS o
volúmenes de red puede hacer falta *polling*: poner `VITE_USE_POLLING: "true"` en
`docker-compose.override.yml` y reiniciar el contenedor del frontend.
