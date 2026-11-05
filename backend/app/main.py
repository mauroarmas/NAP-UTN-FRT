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
    evidencias,
    cambios_consola,
    operaciones,
    calendarios,
    definiciones,
    alertas,
    biblioteca,
    ensayos,
)
import logging
from app.worker import registrar_trabajos
registrar_trabajos()  # Registro de funciones únicamente; no inicia el scheduler.

# Configuración de logging para visibilidad de eventos y correos
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logging.getLogger("app.services.email_service").setLevel(logging.INFO)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """La API no inicia scheduler ni ejecuta migraciones/seeds."""
    if settings.app_env=='production':
        from app.services.puesta_servicio_service import comprobar_arranque
        await comprobar_arranque('api')
    logging.getLogger(__name__).info('API iniciada; los trabajos se ejecutan en el worker independiente')
    yield



app = FastAPI(
    title=settings.app_name,
    description="Portal de gestión y orquestación de servicios para la nube privada de la UTN FRT",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

from app.utils.errors import install_error_handlers
install_error_handlers(app)

# CORS para el frontend React
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.app_frontend_url, *settings.auth_allowed_origins],
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
app.include_router(evidencias.router, prefix="/api/v1")
app.include_router(cambios_consola.router, prefix="/api/v1")
app.include_router(operaciones.router, prefix="/api/v1")
app.include_router(calendarios.router, prefix="/api/v1")
app.include_router(definiciones.router, prefix="/api/v1")
app.include_router(alertas.router, prefix="/api/v1")
app.include_router(biblioteca.router, prefix="/api/v1")
app.include_router(ensayos.router, prefix="/api/v1")


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
