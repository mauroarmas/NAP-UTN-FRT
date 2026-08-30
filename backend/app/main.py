from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.config import get_settings
from app.routers import (
    auth,
    catedras,
    proxmox,
    pedidos,
    templates,
    servicios,
    usuarios,
    metricas,
    capacidad,
    admin_jobs,
)
from app.services import scheduler

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup y shutdown de la aplicación."""
    print(f"🚀 {settings.app_name} iniciando...")
    print(f"📡 Proxmox VE: {settings.proxmox_host}:{settings.proxmox_port}")
    print(f"🗄️  Base de datos: {settings.database_url.split('@')[1] if '@' in settings.database_url else 'N/A'}")

    # Importar los módulos de trabajos registra sus funciones en el planificador.
    from app.services import capacidad_service, vencimiento_service, inactividad_service  # noqa: F401

    scheduler.iniciar()
    print(f"⏱️  Planificador con {len(scheduler.TRABAJOS)} trabajos periódicos")
    yield
    scheduler.detener()
    print("👋 Apagando...")


app = FastAPI(
    title=settings.app_name,
    description="Portal de gestión y orquestación de servicios para la nube privada de la UTN FRT",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# CORS para el frontend React
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite dev server (local sin Docker)
        "http://localhost:5174",  # Vite dev server (Docker Compose)
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registrar routers
app.include_router(auth.router, prefix="/api/v1")
app.include_router(catedras.router, prefix="/api/v1")
app.include_router(proxmox.router, prefix="/api/v1")
app.include_router(pedidos.router, prefix="/api/v1")
app.include_router(templates.router, prefix="/api/v1")
app.include_router(servicios.router, prefix="/api/v1")
app.include_router(usuarios.router, prefix="/api/v1")
app.include_router(metricas.router, prefix="/api/v1")
app.include_router(capacidad.router, prefix="/api/v1")
app.include_router(admin_jobs.router, prefix="/api/v1")


@app.get("/")
async def root():
    return {
        "app": settings.app_name,
        "version": "0.1.0",
        "docs": "/api/docs",
    }


@app.get("/api/v1/health")
async def health_check():
    return {"status": "ok", "env": settings.app_env}
