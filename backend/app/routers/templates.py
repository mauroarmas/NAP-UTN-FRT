from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.recurso_template import RecursoTemplate, TipoRecurso
from app.models.usuario import Usuario
from app.routers.auth import get_current_user, require_admin
from app.schemas.template import TemplateCreate, TemplateResponse

router = APIRouter(prefix="/templates", tags=["Templates"])


@router.get("/", response_model=list[TemplateResponse])
async def listar_templates(
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Lista los templates disponibles. Todos los usuarios autenticados pueden verlos."""
    result = await db.execute(
        select(RecursoTemplate).where(RecursoTemplate.activo == True)
    )
    return result.scalars().all()


@router.get("/{template_id}", response_model=TemplateResponse)
async def obtener_template(
    template_id: int,
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Obtiene un template por ID."""
    template = await db.get(RecursoTemplate, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template no encontrado")
    return template


@router.post("/", response_model=TemplateResponse, status_code=201)
async def crear_template(
    data: TemplateCreate,
    current_user: Usuario = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Crea un nuevo template de recurso. Solo administradores."""
    # Verificar duplicado
    result = await db.execute(
        select(RecursoTemplate).where(RecursoTemplate.nombre == data.nombre)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Ya existe un template con ese nombre")

    template = RecursoTemplate(
        nombre=data.nombre,
        descripcion=data.descripcion,
        tipo=TipoRecurso(data.tipo),
        default_vcpus=data.default_vcpus,
        default_ram_mb=data.default_ram_mb,
        default_disk_gb=data.default_disk_gb,
        os_template=data.os_template,
        config_extra=data.config_extra,
    )

    db.add(template)
    await db.commit()
    await db.refresh(template)

    return template
