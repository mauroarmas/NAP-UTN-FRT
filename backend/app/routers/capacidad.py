"""Panorama de capacidad del clúster.

Admin-only por diseño: es información cuyo dominio es la administración. La
cátedra ve el estado y el vencimiento de sus propios servicios, no la capacidad
física del clúster, que no puede accionar.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.usuario import Usuario
from app.routers.auth import require_admin
from app.services import capacidad_service

router = APIRouter(prefix="/capacidad", tags=["Capacidad"])
logger = logging.getLogger(__name__)


@router.get("/")
async def obtener_capacidad(
    current_user: Usuario = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Capacidad física, comprometida y libre, recalculada en el momento."""
    try:
        return await capacidad_service.panorama(db)
    except Exception as exc:
        # Sin capacidad real no se puede decidir. El sistema no inventa un valor
        # por defecto: aprobar a ciegas es justo lo que hay que evitar.
        logger.warning("No se pudo consultar la capacidad del clúster: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No se pudo consultar la capacidad del clúster Proxmox",
        )
