from fastapi import APIRouter, Depends, HTTPException
from app.services.proxmox_client import get_proxmox_client, ProxmoxClient
from app.models.usuario import Usuario
from app.routers.auth import get_current_user, require_admin

router = APIRouter(prefix="/proxmox", tags=["Proxmox VE"])


@router.get("/status")
async def proxmox_status(
    current_user: Usuario = Depends(require_admin),
    pve: ProxmoxClient = Depends(get_proxmox_client),
):
    """Estado general del clúster Proxmox VE. Solo administradores."""
    try:
        nodes = pve.get_nodes()
        return {
            "status": "connected",
            "nodes": [
                {
                    "node": n["node"],
                    "status": n.get("status", "unknown"),
                    "cpu": n.get("cpu", 0),
                    "maxcpu": n.get("maxcpu", 0),
                    "mem": n.get("mem", 0),
                    "maxmem": n.get("maxmem", 0),
                    "disk": n.get("disk", 0),
                    "maxdisk": n.get("maxdisk", 0),
                }
                for n in nodes
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error al conectar con Proxmox: {str(e)}")


@router.get("/nodes")
async def listar_nodos(
    current_user: Usuario = Depends(require_admin),
    pve: ProxmoxClient = Depends(get_proxmox_client),
):
    """Lista los nodos del clúster con detalles. Solo administradores."""
    try:
        return pve.get_nodes()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error: {str(e)}")


@router.get("/nodes/{node}/lxc")
async def listar_contenedores(
    node: str,
    current_user: Usuario = Depends(require_admin),
    pve: ProxmoxClient = Depends(get_proxmox_client),
):
    """Lista todos los contenedores LXC de un nodo. Solo administradores."""
    try:
        return pve.list_lxc(node)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error: {str(e)}")


@router.get("/resources")
async def recursos_cluster(
    current_user: Usuario = Depends(require_admin),
    pve: ProxmoxClient = Depends(get_proxmox_client),
):
    """Todos los recursos del clúster (VMs, CTs, nodos, storage). Solo administradores."""
    try:
        return pve.get_cluster_resources()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error: {str(e)}")
