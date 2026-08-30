from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models.recurso_template import RecursoTemplate, TipoRecurso
from app.models.usuario import Usuario, RolUsuario
from app.routers.auth import get_current_user, require_admin
from app.models.pedido import Pedido, EstadoPedido
from app.models.servicio import Servicio
from app.schemas.template import (
    AlcanceDelCambio,
    TemplateCreate,
    TemplateResponse,
    TemplateUpdate,
)
from app.services.limites_service import validar_disco

router = APIRouter(prefix="/templates", tags=["Templates"])


@router.get("/", response_model=list[TemplateResponse])
async def listar_templates(
    incluir_retiradas: bool = False,
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Lista el catálogo de plantillas.

    Por defecto solo las activas: es el catálogo que la cátedra puede pedir.
    `incluir_retiradas` las trae todas, y es lo que le permite al administrador
    encontrar una plantilla que retiró para volver a habilitarla. Sin eso, retirar
    sería un camino de ida desde la interfaz.
    """
    consulta = select(RecursoTemplate)
    if not (incluir_retiradas and current_user.rol == RolUsuario.ADMIN):
        consulta = consulta.where(RecursoTemplate.activo == True)
    result = await db.execute(consulta)
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

    # Tope de disco por contenedor: superarlo exige justificación registrada.
    validar_disco(data.default_disk_gb, data.justificacion_disco)

    template = RecursoTemplate(
        nombre=data.nombre,
        descripcion=data.descripcion,
        tipo=TipoRecurso(data.tipo),
        default_vcpus=data.default_vcpus,
        default_ram_mb=data.default_ram_mb,
        default_disk_gb=data.default_disk_gb,
        justificacion_disco=data.justificacion_disco,
        os_template=data.os_template,
        config_extra=data.config_extra,
    )

    db.add(template)
    await db.commit()
    await db.refresh(template)

    return template


async def _alcance_del_cambio(db: AsyncSession, template_id: int) -> AlcanceDelCambio:
    """Qué NO se ve afectado por corregir esta plantilla (FR-003).

    Los servicios ya desplegados guardan sus propios recursos, y los pedidos
    aprobados se desplegarán con la capacidad que reservaron (FR-018). Contarlos
    sirve para decírselo al administrador, no para impedirle nada.
    """
    servicios = await db.execute(
        select(func.count())
        .select_from(Servicio)
        .where(Servicio.template_id == template_id, Servicio.deleted_at.is_(None))
    )
    pendientes = await db.execute(
        select(func.count())
        .select_from(Pedido)
        .where(
            Pedido.template_id == template_id,
            Pedido.estado == EstadoPedido.APROBADO,
            Pedido.deleted_at.is_(None),
            ~Pedido.id.in_(select(Servicio.pedido_id).where(Servicio.pedido_id.isnot(None))),
        )
    )
    return AlcanceDelCambio(
        servicios_desplegados=servicios.scalar_one(),
        pedidos_aprobados_pendientes=pendientes.scalar_one(),
    )


@router.patch("/{template_id}", response_model=TemplateResponse)
async def actualizar_template(
    template_id: int,
    data: TemplateUpdate,
    current_user: Usuario = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Corrige una plantilla existente, o la retira del catálogo.

    Una plantilla mal cargada solía quedar inservible para siempre: se podía
    crear pero no corregir, y seguía ofreciéndose en el catálogo hasta que un
    despliegue fallaba, mucho después de que la cátedra pidiera y el
    administrador comprometiera capacidad. La única salida era un UPDATE a mano
    sobre la base, que la constitución prohíbe.

    Lo que esta corrección **no** hace: tocar los servicios ya desplegados (que
    guardan sus propios recursos) ni los pedidos ya aprobados (que se despliegan
    con lo que reservaron). Rige de acá en adelante.
    """
    template = await db.get(RecursoTemplate, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template no encontrado")

    cambios = data.model_dump(exclude_unset=True)

    # `tipo` no se acepta ni siquiera si el cliente lo manda: cambiar un LXC por
    # una VM altera lo que ya se aprobó sobre esta plantilla (regla T4).
    if "tipo" in cambios:
        raise HTTPException(
            status_code=400,
            detail="El tipo de una plantilla no se puede cambiar; creá una nueva",
        )

    if "nombre" in cambios and cambios["nombre"] != template.nombre:
        duplicado = await db.execute(
            select(RecursoTemplate).where(
                RecursoTemplate.nombre == cambios["nombre"],
                RecursoTemplate.id != template_id,
            )
        )
        if duplicado.scalar_one_or_none():
            raise HTTPException(
                status_code=409, detail="Ya existe otra plantilla con ese nombre"
            )

    # El tope de disco rige igual que en el alta. Se evalúa contra los valores
    # que quedarían después de aplicar el cambio, no contra los enviados: subir
    # el disco y agregar la justificación en la misma operación es válido.
    disco = cambios.get("default_disk_gb", template.default_disk_gb)
    justificacion = cambios.get("justificacion_disco", template.justificacion_disco)
    validar_disco(disco, justificacion)

    for campo, valor in cambios.items():
        setattr(template, campo, valor)

    await db.commit()
    await db.refresh(template)

    respuesta = TemplateResponse.model_validate(template)
    respuesta.alcance_del_cambio = await _alcance_del_cambio(db, template_id)
    return respuesta
