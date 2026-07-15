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

router = APIRouter(prefix="/catedras", tags=["Cátedras"])


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
    for field, value in update_data.items():
        setattr(catedra, field, value)

    await db.commit()
    await db.refresh(catedra)

    return catedra
