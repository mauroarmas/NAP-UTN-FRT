from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.servicio import Servicio, EstadoServicio
from app.models.usuario import Usuario, RolUsuario
from app.routers.auth import get_current_user, require_admin
from app.schemas.servicio import ServicioResponse, DesplegarRequest
from app.services.orquestacion_service import (
    desplegar_pedido,
    detener_servicio,
    iniciar_servicio,
    eliminar_servicio,
)
from app.utils.soft_delete import excluir_dados_de_baja, vigente_o_404

router = APIRouter(prefix="/servicios", tags=["Servicios"])


@router.get("/", response_model=list[ServicioResponse])
async def listar_servicios(
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Lista servicios vigentes. Admin ve todos, cátedra ve solo los suyos."""
    query = excluir_dados_de_baja(select(Servicio), Servicio).order_by(
        Servicio.deployed_at.desc()
    )

    if current_user.rol != RolUsuario.ADMIN:
        query = query.where(Servicio.catedra_id == current_user.catedra_id)

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{servicio_id}", response_model=ServicioResponse)
async def obtener_servicio(
    servicio_id: int,
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Obtiene un servicio vigente por ID."""
    servicio = vigente_o_404(
        await db.get(Servicio, servicio_id), "Servicio no encontrado"
    )

    if current_user.rol != RolUsuario.ADMIN and servicio.catedra_id != current_user.catedra_id:
        raise HTTPException(status_code=403, detail="Sin permisos")

    return servicio


@router.post("/desplegar/{pedido_id}", response_model=ServicioResponse)
async def desplegar(
    pedido_id: int,
    body: DesplegarRequest = DesplegarRequest(),
    current_user: Usuario = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Despliega un pedido APROBADO creando el LXC en Proxmox VE.
    Ejecuta la transición completa: APROBADO → EN_DESPLIEGUE → ACTIVO (o ERROR).
    """
    return await desplegar_pedido(
        db=db,
        pedido_id=pedido_id,
        admin=current_user,
        node=body.node,
        storage=body.storage,
    )


@router.post("/{servicio_id}/start", response_model=ServicioResponse)
async def iniciar(
    servicio_id: int,
    current_user: Usuario = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Inicia un servicio detenido en Proxmox."""
    return await iniciar_servicio(db, servicio_id, current_user)


@router.post("/{servicio_id}/stop", response_model=ServicioResponse)
async def detener(
    servicio_id: int,
    current_user: Usuario = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Detiene un servicio en ejecución en Proxmox."""
    return await detener_servicio(db, servicio_id, current_user)


@router.delete("/{servicio_id}")
async def eliminar(
    servicio_id: int,
    current_user: Usuario = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Da de baja un servicio: libera su contenedor en Proxmox y marca el registro.

    La baja es lógica: la fila permanece para poder reconstruir el consumo
    histórico de la cátedra. Si no se pudo liberar el recurso real, el registro
    no se marca (evita contenedores vivos sin registro operativo).

    Códigos: 200 baja exitosa (o ya estaba dada de baja, idempotente) ·
    403 sin permisos de administrador · 404 servicio inexistente ·
    502 falló la liberación en Proxmox (el registro queda intacto).
    """
    return await eliminar_servicio(db, servicio_id, current_user)


@router.get("/{servicio_id}/status")
async def estado_en_proxmox(
    servicio_id: int,
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Consulta el estado real del contenedor directamente en Proxmox."""
    from app.services.proxmox_client import get_proxmox_client

    servicio = vigente_o_404(
        await db.get(Servicio, servicio_id), "Servicio no encontrado"
    )

    if current_user.rol != RolUsuario.ADMIN and servicio.catedra_id != current_user.catedra_id:
        raise HTTPException(status_code=403, detail="Sin permisos")

    if not servicio.proxmox_vmid or not servicio.proxmox_node:
        raise HTTPException(status_code=400, detail="Servicio sin VMID asignado")

    try:
        pve = get_proxmox_client()
        status = pve.get_lxc_status(servicio.proxmox_node, int(servicio.proxmox_vmid))
        return {
            "servicio_id": servicio_id,
            "vmid": servicio.proxmox_vmid,
            "node": servicio.proxmox_node,
            "proxmox_status": status,
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Error consultando Proxmox: {str(exc)}")
