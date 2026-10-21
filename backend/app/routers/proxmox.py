from fastapi import APIRouter, Depends, HTTPException
from app.services.infraestructura_io import consultar, InfraNoVerificable
from app.utils.errors import error
from app.models.usuario import Usuario
from app.routers.auth import require_admin

router = APIRouter(prefix="/proxmox", tags=["Proxmox VE"])


async def _read(method, *args):
    try:
        observation = await consultar(method, *args)
        if observation.estado != 'presente':
            raise InfraNoVerificable()
        return observation.valor
    except InfraNoVerificable:
        raise error(502, 'infraestructura_no_verificable', 'No se pudo consultar Proxmox', reintentable=True) from None


@router.get("/status")
async def proxmox_status(
    current_user: Usuario = Depends(require_admin),
):
    """Estado general del clúster Proxmox VE. Solo administradores."""
    try:
        nodes = await _read('get_nodes')
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
    except HTTPException:
        raise
    except Exception:
        raise error(502, 'infraestructura_no_verificable', 'No se pudo consultar Proxmox', reintentable=True) from None


@router.get("/nodes")
async def listar_nodos(
    current_user: Usuario = Depends(require_admin),
):
    """Lista los nodos del clúster con detalles. Solo administradores."""
    try:
        return await _read('get_nodes')
    except HTTPException:
        raise
    except Exception:
        raise error(502, 'infraestructura_no_verificable', 'No se pudo consultar Proxmox', reintentable=True) from None


@router.get("/nodes/{node}/lxc")
async def listar_contenedores(
    node: str,
    current_user: Usuario = Depends(require_admin),
):
    """Lista todos los contenedores LXC de un nodo. Solo administradores."""
    try:
        return await _read('list_lxc', node)
    except HTTPException:
        raise
    except Exception:
        raise error(502, 'infraestructura_no_verificable', 'No se pudo consultar Proxmox', reintentable=True) from None


@router.get("/templates")
async def listar_templates_disponibles(
    node: str | None = None,
    storage: str = "local",
    current_user: Usuario = Depends(require_admin),
):
    """Lista los OS templates (vztmpl) disponibles en un storage de Proxmox. Solo administradores."""
    try:
        target_node = node
        if not target_node:
            nodes = await _read('get_nodes')
            online = [n for n in nodes if n.get("status") == "online"]
            if not online:
                raise HTTPException(status_code=502, detail="No hay nodos Proxmox disponibles")
            target_node = online[0]["node"]

        content = await _read('get_available_templates', target_node, storage)
        return [
            {
                "volid": item["volid"],
                "size": item.get("size"),
                "format": item.get("format"),
            }
            for item in content
            if item.get("content") == "vztmpl"
        ]
    except HTTPException:
        raise
    except Exception:
        raise error(502, 'infraestructura_no_verificable', 'No se pudo consultar Proxmox', reintentable=True) from None


@router.get("/storage")
async def listar_storages(
    current_user: Usuario = Depends(require_admin),
):
    """
    Espacio real de cada storage configurado del clúster. Solo administradores.

    Es distinto del `disk`/`maxdisk` de un nodo, que mide únicamente el sistema
    de archivos raíz del host: los contenedores no se crean ahí sino en un
    storage con contenido `rootdir`/`images` (típicamente `local-lvm`). Ese es
    el número que decide si un LXC nuevo entra, y por eso viaja marcado con
    `aloja_contenedores`.
    """
    try:
        storages = await _read('get_cluster_resources', 'storage')
    except HTTPException:
        raise
    except Exception:
        raise error(502, 'infraestructura_no_verificable', 'No se pudo consultar Proxmox', reintentable=True) from None

    return [
        {
            "storage": s.get("storage"),
            "node": s.get("node"),
            "tipo": s.get("plugintype"),
            "contenido": s.get("content", ""),
            "estado": s.get("status"),
            "compartido": bool(s.get("shared")),
            "usado_bytes": s.get("disk", 0),
            "total_bytes": s.get("maxdisk", 0),
            "aloja_contenedores": any(
                c in (s.get("content") or "") for c in ("rootdir", "images")
            ),
        }
        for s in storages
    ]


@router.get("/resources")
async def recursos_cluster(
    current_user: Usuario = Depends(require_admin),
):
    """Todos los recursos del clúster (VMs, CTs, nodos, storage). Solo administradores."""
    try:
        return await _read('get_cluster_resources')
    except HTTPException:
        raise
    except Exception:
        raise error(502, 'infraestructura_no_verificable', 'No se pudo consultar Proxmox', reintentable=True) from None
