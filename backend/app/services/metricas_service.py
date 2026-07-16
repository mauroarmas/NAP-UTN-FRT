"""
Servicio de métricas: captura snapshots de recursos desde Proxmox
y los persiste en metricas_snapshots para análisis histórico.
"""
import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.models.metrica import MetricaSnapshot
from app.models.servicio import Servicio, EstadoServicio
from app.services.proxmox_client import get_proxmox_client

logger = logging.getLogger(__name__)


async def capturar_snapshot_servicio(
    db: AsyncSession,
    servicio: Servicio,
) -> MetricaSnapshot | None:
    """
    Consulta Proxmox por el estado actual de un servicio LXC
    y guarda un snapshot de métricas en la DB.
    Retorna None si el contenedor no está corriendo.
    """
    if not servicio.proxmox_vmid or not servicio.proxmox_node:
        return None

    pve = get_proxmox_client()
    vmid = int(servicio.proxmox_vmid)
    node = servicio.proxmox_node

    try:
        status = pve.get_lxc_status(node, vmid)
    except Exception as exc:
        logger.warning(f"No se pudo obtener status VMID={vmid}: {exc}")
        return None

    if status.get("status") != "running":
        return None

    # --- Extraer métricas ---
    # CPU: Proxmox devuelve fracción (0.0-1.0) × nCPUs
    cpu_pct = round(status.get("cpu", 0) * 100, 2)

    # RAM: mem y maxmem en bytes
    ram_mb = round(status.get("mem", 0) / (1024 * 1024), 2)

    # Disco: disk y maxdisk en bytes
    disk_gb = round(status.get("disk", 0) / (1024 * 1024 * 1024), 3)

    # Red: netin / netout en bytes acumulados
    net_in  = float(status.get("netin",  0))
    net_out = float(status.get("netout", 0))

    snapshot = MetricaSnapshot(
        servicio_id=servicio.id,
        cpu_usage_percent=cpu_pct,
        ram_usage_mb=ram_mb,
        disk_usage_gb=disk_gb,
        net_in_bytes=net_in,
        net_out_bytes=net_out,
        timestamp=datetime.utcnow(),
    )
    db.add(snapshot)
    await db.commit()
    await db.refresh(snapshot)

    return snapshot


async def capturar_todos_los_servicios(db: AsyncSession) -> dict:
    """
    Captura métricas de todos los servicios RUNNING.
    Ideal para llamar periódicamente (ej: cada 60s).
    """
    result = await db.execute(
        select(Servicio).where(Servicio.estado == EstadoServicio.RUNNING)
    )
    servicios = result.scalars().all()

    capturados = 0
    errores = 0

    for srv in servicios:
        try:
            snap = await capturar_snapshot_servicio(db, srv)
            if snap:
                capturados += 1
        except Exception as exc:
            logger.error(f"Error capturando métricas servicio {srv.id}: {exc}")
            errores += 1

    return {
        "servicios_totales": len(servicios),
        "capturados": capturados,
        "errores": errores,
        "timestamp": datetime.utcnow().isoformat(),
    }


async def obtener_historial(
    db: AsyncSession,
    servicio_id: int,
    limit: int = 60,
) -> list[MetricaSnapshot]:
    """Devuelve los últimos N snapshots de un servicio."""
    result = await db.execute(
        select(MetricaSnapshot)
        .where(MetricaSnapshot.servicio_id == servicio_id)
        .order_by(desc(MetricaSnapshot.timestamp))
        .limit(limit)
    )
    # Devolver en orden cronológico (más antiguo primero para los gráficos)
    return list(reversed(result.scalars().all()))


async def obtener_ultimo_snapshot(
    db: AsyncSession,
    servicio_id: int,
) -> MetricaSnapshot | None:
    """Devuelve el snapshot más reciente de un servicio."""
    result = await db.execute(
        select(MetricaSnapshot)
        .where(MetricaSnapshot.servicio_id == servicio_id)
        .order_by(desc(MetricaSnapshot.timestamp))
        .limit(1)
    )
    return result.scalar_one_or_none()
