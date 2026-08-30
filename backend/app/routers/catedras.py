"""Cátedras: alta, reasignación de titular y consulta de consumo.

Ya no hay cuota que validar. Una cátedra tiene los servicios que le fueron
aprobados; el control de recursos vive en la aprobación del pedido, contra la
capacidad real del clúster. Lo que sí se conserva de esta pantalla es el
**consumo vigente**, que la cátedra necesita ver aunque ya no tenga techo.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
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
from app.services.acceso_service import catedras_visibles, es_visible

router = APIRouter(prefix="/catedras", tags=["Cátedras"])
logger = logging.getLogger(__name__)


async def _titular_de(db: AsyncSession, catedra: Catedra) -> dict | None:
    if catedra.titular_id is None:
        return None
    titular = await db.get(Usuario, catedra.titular_id)
    if titular is None:
        return None
    return {"id": titular.id, "nombre": titular.nombre, "username": titular.username}


async def _a_respuesta(db: AsyncSession, catedra: Catedra) -> CatedraResponse:
    return CatedraResponse(
        id=catedra.id,
        nombre=catedra.nombre,
        descripcion=catedra.descripcion,
        activa=catedra.activa,
        created_at=catedra.created_at,
        titular_id=catedra.titular_id,
        titular=await _titular_de(db, catedra),
    )


@router.get("/mias", response_model=list[CatedraResponse])
async def mis_catedras(
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Las cátedras de la persona autenticada.

    Reemplaza al viejo `/mi-catedra`: ya no hay una cátedra en singular.
    """
    result = await db.execute(
        select(Catedra)
        .where(Catedra.id.in_(await catedras_visibles(db, current_user)))
        .order_by(Catedra.nombre)
    )
    return [await _a_respuesta(db, c) for c in result.scalars().all()]


@router.get("/", response_model=list[CatedraResponse])
async def listar_catedras(
    sin_titular: bool = Query(
        False, description="Solo las que todavía no tienen responsable"
    ),
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Lista cátedras. Admin ve todas; la cátedra ve solo las suyas."""
    query = select(Catedra).order_by(Catedra.nombre)
    if current_user.rol.value != "admin":
        query = query.where(Catedra.id.in_(await catedras_visibles(db, current_user)))
    if sin_titular:
        query = query.where(Catedra.titular_id.is_(None))

    result = await db.execute(query)
    return [await _a_respuesta(db, c) for c in result.scalars().all()]


@router.get("/{catedra_id}", response_model=CatedraConUso)
async def obtener_catedra(
    catedra_id: int,
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cátedra con su consumo vigente (sin referencia a ningún techo)."""
    if not await es_visible(db, current_user, catedra_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para ver esta cátedra",
        )

    catedra = (
        await db.execute(select(Catedra).where(Catedra.id == catedra_id))
    ).scalar_one_or_none()
    if not catedra:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Cátedra no encontrada"
        )

    servicios = (
        (
            await db.execute(
                select(Servicio).where(
                    Servicio.catedra_id == catedra_id,
                    Servicio.estado == EstadoServicio.RUNNING,
                    # Lo dado de baja no cuenta como uso de recursos.
                    Servicio.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )

    base = await _a_respuesta(db, catedra)
    return CatedraConUso(
        **base.model_dump(),
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
    """Crea una cátedra y le asigna responsable. Solo administradores."""
    if data.titular_id is not None:
        titular = await db.get(Usuario, data.titular_id)
        if titular is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Titular no encontrado"
            )

    # El nombre ya no es único a nivel global: dos personas pueden dictar
    # materias homónimas. Lo que no puede repetirse es nombre + titular.
    duplicada = (
        await db.execute(
            select(Catedra).where(
                Catedra.nombre == data.nombre, Catedra.titular_id == data.titular_id
            )
        )
    ).scalar_one_or_none()
    if duplicada:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Esa persona ya tiene una cátedra con ese nombre",
        )

    catedra = Catedra(**data.model_dump())
    db.add(catedra)
    await db.commit()
    await db.refresh(catedra)

    return await _a_respuesta(db, catedra)


@router.patch("/{catedra_id}", response_model=CatedraResponse)
async def actualizar_catedra(
    catedra_id: int,
    data: CatedraUpdate,
    confirmar: bool = Query(
        False, description="Confirma la baja aunque tenga servicios vigentes"
    ),
    current_user: Usuario = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Actualiza una cátedra, incluida la reasignación de titular.

    Los pedidos, servicios e historial pertenecen a la cátedra, no a la persona:
    reasignar el titular no mueve ni pierde nada de eso.
    """
    catedra = (
        await db.execute(select(Catedra).where(Catedra.id == catedra_id))
    ).scalar_one_or_none()
    if not catedra:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Cátedra no encontrada"
        )

    update_data = data.model_dump(exclude_unset=True)

    if update_data.get("titular_id") is not None:
        if await db.get(Usuario, update_data["titular_id"]) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Titular no encontrado"
            )

    # Desactivar una cátedra con servicios vigentes exige confirmación: son
    # recursos reales que quedarían sin responsable a la vista.
    if update_data.get("activa") is False and catedra.activa:
        vigentes = (
            (
                await db.execute(
                    select(Servicio).where(
                        Servicio.catedra_id == catedra_id,
                        Servicio.deleted_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        if vigentes and not confirmar:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "codigo": "servicios_vigentes",
                    "mensaje": (
                        f"La cátedra tiene {len(vigentes)} servicio(s) vigente(s). "
                        "Confirmá la baja si querés continuar."
                    ),
                    "servicios_afectados": len(vigentes),
                },
            )

    for field, value in update_data.items():
        setattr(catedra, field, value)

    await db.commit()
    await db.refresh(catedra)

    return await _a_respuesta(db, catedra)
