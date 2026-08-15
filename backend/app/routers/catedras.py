import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.catedra import Catedra
from app.models.servicio import Servicio, EstadoServicio
from app.models.usuario import Usuario
from app.routers.auth import require_admin, get_current_user
from app.schemas.catedra import (
    CatedraCreate,
    CatedraUpdate,
    CatedraResponse,
    CatedraConUso,
)
from app.services.proxmox_client import get_proxmox_client, ProxmoxClient

router = APIRouter(prefix="/catedras", tags=["Cátedras"])
logger = logging.getLogger(__name__)


def _capacidad_cluster(pve: ProxmoxClient) -> dict:
    """Capacidad total de los nodos online del clúster, en las unidades de las cuotas."""
    online = [n for n in pve.get_nodes() if n.get("status") == "online"]
    return {
        "vcpus": sum(n.get("maxcpu", 0) for n in online),
        "ram_mb": sum(n.get("maxmem", 0) for n in online) // (1024 * 1024),
        "storage_gb": sum(n.get("maxdisk", 0) for n in online) // (1024 ** 3),
    }


async def _cuotas_comprometidas(db: AsyncSession, excluir_id: int | None = None) -> dict:
    """Suma de cuotas de las cátedras activas (la capacidad que ya está reservada)."""
    query = select(Catedra).where(Catedra.activa.is_(True))
    if excluir_id is not None:
        query = query.where(Catedra.id != excluir_id)
    catedras = (await db.execute(query)).scalars().all()
    return {
        "vcpus": sum(c.cuota_vcpus for c in catedras),
        "ram_mb": sum(c.cuota_ram_mb for c in catedras),
        "storage_gb": sum(c.cuota_storage_gb for c in catedras),
    }


def _validar_contra_capacidad(
    vcpus: int, ram_mb: int, storage_gb: int, comprometido: dict, capacidad: dict
) -> None:
    """Rechaza la cuota si, sumada a lo ya comprometido, supera la capacidad del clúster."""
    chequeos = [
        ("vcpus", "vCPUs", "", vcpus),
        ("ram_mb", "RAM", " MB", ram_mb),
        ("storage_gb", "Disco", " GB", storage_gb),
    ]
    errores = [
        f"{etiqueta}: {comprometido[clave] + valor}{unidad} solicitados supera la "
        f"capacidad del clúster Proxmox ({capacidad[clave]}{unidad})"
        for clave, etiqueta, unidad, valor in chequeos
        if comprometido[clave] + valor > capacidad[clave]
    ]
    if errores:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La cuota solicitada supera la capacidad del clúster Proxmox: "
            + "; ".join(errores),
        )


async def _validar_cuota_o_advertir(
    db: AsyncSession,
    pve: ProxmoxClient,
    vcpus: int,
    ram_mb: int,
    storage_gb: int,
    excluir_id: int | None = None,
) -> None:
    """
    Valida la cuota contra la capacidad real del clúster Proxmox.

    Si Proxmox no responde, no bloquea la gestión de cátedras: solo registra una
    advertencia, ya que la validación de capacidad es una ayuda de planificación,
    no un control de seguridad.
    """
    try:
        capacidad = _capacidad_cluster(pve)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(f"No se pudo validar la cuota contra Proxmox: {exc}")
        return

    comprometido = await _cuotas_comprometidas(db, excluir_id=excluir_id)
    _validar_contra_capacidad(vcpus, ram_mb, storage_gb, comprometido, capacidad)


@router.get("/", response_model=list[CatedraResponse])
async def listar_catedras(
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Lista todas las cátedras. Admin ve todas, cátedra ve solo la suya."""
    if current_user.rol.value == "admin":
        result = await db.execute(select(Catedra))
    else:
        result = await db.execute(
            select(Catedra).where(Catedra.id == current_user.catedra_id)
        )
    return result.scalars().all()


@router.get("/{catedra_id}", response_model=CatedraConUso)
async def obtener_catedra(
    catedra_id: int,
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Obtiene una cátedra con información de uso de recursos."""
    # Verificar permisos
    if (
        current_user.rol.value != "admin"
        and current_user.catedra_id != catedra_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para ver esta cátedra",
        )

    result = await db.execute(select(Catedra).where(Catedra.id == catedra_id))
    catedra = result.scalar_one_or_none()

    if not catedra:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cátedra no encontrada",
        )

    # Calcular uso actual
    servicios_result = await db.execute(
        select(Servicio).where(
            Servicio.catedra_id == catedra_id,
            Servicio.estado == EstadoServicio.RUNNING,
            # Lo dado de baja no cuenta como uso de recursos (FR-012)
            Servicio.deleted_at.is_(None),
        )
    )
    servicios = servicios_result.scalars().all()

    return CatedraConUso(
        id=catedra.id,
        nombre=catedra.nombre,
        descripcion=catedra.descripcion,
        cuota_vcpus=catedra.cuota_vcpus,
        cuota_ram_mb=catedra.cuota_ram_mb,
        cuota_storage_gb=catedra.cuota_storage_gb,
        activa=catedra.activa,
        created_at=catedra.created_at,
        vcpus_en_uso=sum(s.vcpus_asignados for s in servicios),
        ram_en_uso_mb=sum(s.ram_asignada_mb for s in servicios),
        storage_en_uso_gb=sum(s.disk_asignado_gb for s in servicios),
        servicios_activos=len(servicios),
    )


@router.post("/", response_model=CatedraResponse, status_code=status.HTTP_201_CREATED)
async def crear_catedra(
    data: CatedraCreate,
    current_user: Usuario = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    pve: ProxmoxClient = Depends(get_proxmox_client),
):
    """Crea una nueva cátedra. Solo administradores."""
    # Verificar que no exista
    result = await db.execute(
        select(Catedra).where(Catedra.nombre == data.nombre)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya existe una cátedra con ese nombre",
        )

    await _validar_cuota_o_advertir(
        db, pve, data.cuota_vcpus, data.cuota_ram_mb, data.cuota_storage_gb
    )

    catedra = Catedra(**data.model_dump())
    db.add(catedra)
    await db.commit()
    await db.refresh(catedra)

    return catedra


@router.patch("/{catedra_id}", response_model=CatedraResponse)
async def actualizar_catedra(
    catedra_id: int,
    data: CatedraUpdate,
    current_user: Usuario = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    pve: ProxmoxClient = Depends(get_proxmox_client),
):
    """Actualiza una cátedra. Solo administradores."""
    result = await db.execute(select(Catedra).where(Catedra.id == catedra_id))
    catedra = result.scalar_one_or_none()

    if not catedra:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cátedra no encontrada",
        )

    update_data = data.model_dump(exclude_unset=True)

    # Solo re-validar contra Proxmox si cambia algo que afecte lo comprometido:
    # las cuotas mismas, o una reactivación (activa=False -> True vuelve a reservar).
    cambia_cuota = any(
        k in update_data for k in ("cuota_vcpus", "cuota_ram_mb", "cuota_storage_gb")
    )
    reactiva = update_data.get("activa") is True and not catedra.activa
    if cambia_cuota or reactiva:
        await _validar_cuota_o_advertir(
            db,
            pve,
            update_data.get("cuota_vcpus", catedra.cuota_vcpus),
            update_data.get("cuota_ram_mb", catedra.cuota_ram_mb),
            update_data.get("cuota_storage_gb", catedra.cuota_storage_gb),
            excluir_id=catedra_id,
        )

    for field, value in update_data.items():
        setattr(catedra, field, value)

    await db.commit()
    await db.refresh(catedra)

    return catedra
