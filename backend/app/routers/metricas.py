from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from datetime import datetime

from app.database import get_db
from app.models.metrica import MetricaSnapshot
from app.models.servicio import Servicio, EstadoServicio
from app.models.usuario import Usuario, RolUsuario
from app.routers.auth import get_current_user, require_admin
from app.services.acceso_service import catedras_visibles, es_visible
from app.services.metricas_service import (
    capturar_snapshot_servicio,
    capturar_todos_los_servicios,
    obtener_historial,
    obtener_ultimo_snapshot,
)
from app.utils.soft_delete import excluir_dados_de_baja, vigente_o_404

router = APIRouter(prefix="/metricas", tags=["Métricas"])


# ── Schemas inline ──────────────────────────────────────────────
class SnapshotResponse(BaseModel):
    id: int
    servicio_id: int
    cpu_usage_percent: float
    ram_usage_mb: float
    disk_usage_gb: float
    net_in_bytes: float
    net_out_bytes: float
    timestamp: datetime

    model_config = {"from_attributes": True}


class ServicioConMetrica(BaseModel):
    servicio_id: int
    vmid: str | None
    hostname: str | None
    node: str | None
    estado: str
    vcpus: int
    ram_max_mb: int
    disk_max_gb: int
    ultimo_snapshot: SnapshotResponse | None = None


# ── Endpoints ────────────────────────────────────────────────────

@router.post("/capturar", summary="Captura métricas de todos los servicios RUNNING")
async def capturar_metricas(
    current_user: Usuario = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Dispara una captura de métricas manual para todos los servicios activos."""
    resultado = await capturar_todos_los_servicios(db)
    return resultado


@router.post("/capturar/{servicio_id}", response_model=SnapshotResponse)
async def capturar_servicio(
    servicio_id: int,
    current_user: Usuario = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Captura métricas de un servicio específico ahora mismo."""
    servicio = vigente_o_404(
        await db.get(Servicio, servicio_id), "Servicio no encontrado"
    )

    snap = await capturar_snapshot_servicio(db, servicio)
    if not snap:
        raise HTTPException(
            status_code=409,
            detail="No se pudo capturar métricas (el contenedor no está running o no tiene VMID)",
        )
    return snap


@router.get("/resumen", summary="Estado actual de todos los servicios con su última métrica")
async def resumen_servicios(
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Devuelve todos los servicios con su último snapshot de métricas.
    Admin ve todos; cátedra ve solo los suyos.
    """
    from app.services.proxmox_client import get_proxmox_client

    query = excluir_dados_de_baja(select(Servicio), Servicio)
    if current_user.rol != RolUsuario.ADMIN:
        query = query.where(
            Servicio.catedra_id.in_(await catedras_visibles(db, current_user))
        )

    result = await db.execute(query)
    servicios = result.scalars().all()

    pve = get_proxmox_client()
    resumen = []

    for srv in servicios:
        ultimo = await obtener_ultimo_snapshot(db, srv.id)

        # Obtener maxdisk real de Proxmox para cálculo preciso del % de disco
        disk_max_real_gb = float(srv.disk_asignado_gb)
        if srv.proxmox_vmid and srv.proxmox_node and srv.estado.value in ("RUNNING", "STOPPED"):
            try:
                status = pve.get_lxc_status(srv.proxmox_node, int(srv.proxmox_vmid))
                if status.get("maxdisk"):
                    disk_max_real_gb = round(status["maxdisk"] / (1024 ** 3), 3)
            except Exception:
                pass

        resumen.append({
            "servicio_id":       srv.id,
            "vmid":              srv.proxmox_vmid,
            "hostname":          srv.hostname,
            "node":              srv.proxmox_node,
            "estado":            srv.estado.value,
            "ip_address":        srv.ip_address,
            "vcpus":             srv.vcpus_asignados,
            "ram_max_mb":        srv.ram_asignada_mb,
            "disk_max_gb":       srv.disk_asignado_gb,
            "disk_max_real_gb":  disk_max_real_gb,
            "ultimo_snapshot": {
                "id":                ultimo.id,
                "servicio_id":       ultimo.servicio_id,
                "cpu_usage_percent": ultimo.cpu_usage_percent,
                "ram_usage_mb":      ultimo.ram_usage_mb,
                "disk_usage_gb":     ultimo.disk_usage_gb,
                "net_in_bytes":      ultimo.net_in_bytes,
                "net_out_bytes":     ultimo.net_out_bytes,
                "timestamp":         ultimo.timestamp,
            } if ultimo else None,
        })

    return resumen


@router.get("/{servicio_id}/historial", response_model=list[SnapshotResponse])
async def historial_servicio(
    servicio_id: int,
    limit: int = Query(default=60, le=500, description="Máximo de puntos históricos"),
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Devuelve el historial de métricas de un servicio (orden cronológico)."""
    servicio = vigente_o_404(
        await db.get(Servicio, servicio_id), "Servicio no encontrado"
    )

    if not await es_visible(db, current_user, servicio.catedra_id):
        raise HTTPException(status_code=403, detail="Sin permisos")

    return await obtener_historial(db, servicio_id, limit)


@router.get("/{servicio_id}/ultimo", response_model=SnapshotResponse)
async def ultimo_snapshot(
    servicio_id: int,
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Devuelve el último snapshot de métricas de un servicio."""
    servicio = vigente_o_404(
        await db.get(Servicio, servicio_id), "Servicio no encontrado"
    )

    snap = await obtener_ultimo_snapshot(db, servicio_id)
    if not snap:
        raise HTTPException(status_code=404, detail="Sin métricas aún. Ejecutá una captura primero.")

    return snap
