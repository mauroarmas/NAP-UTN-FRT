from fastapi import APIRouter, Depends, HTTPException, status, Header
from fastapi.responses import JSONResponse
from app.schemas.aplicacion import AgregarAplicacion, RevisarAplicacion
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from types import SimpleNamespace
from typing import Literal

from app.database import get_db
from app.models.recurso_template import RecursoTemplate, TipoRecurso
from app.models.usuario import Usuario, RolUsuario
from app.routers.auth import get_current_user, require_admin
from app.models.pedido import Pedido, EstadoPedido, ModeloServicio
from app.models.servicio import Servicio
from app.schemas.template import (
    AlcanceDelCambio,
    TemplateCreate,
    TemplateResponse,
    TemplateUpdate,
)
from app.services.perfiles_service import exigir_definicion, anexar_disponibilidad
from app.utils.errors import error
from app.schemas.tamanos import TAMANOS, validar_tamano

router = APIRouter(prefix="/templates", tags=["Templates"])


@router.get('/tamanos')
async def listar_tamanos(current_user: Usuario = Depends(require_admin)):
    return [{'id': name, 'nombre': name.title(), **resources} for name, resources in TAMANOS.items()]


@router.post('/sincronizar-iaas')
async def sincronizar_iaas(current_user: Usuario = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    from app.services.bases_iaas_service import sincronizar
    count = await sincronizar(db)
    await db.commit()
    return {'disponibles': count}


@router.post('/aplicaciones',status_code=201)
async def agregar_aplicacion(data:AgregarAplicacion,clave:str=Header(alias='Idempotency-Key'),
        current_user:Usuario=Depends(require_admin),db:AsyncSession=Depends(get_db)):
    from app.services.configuracion_despliegue_service import change
    result=await change(db,actor=current_user,body=data,clave=clave)
    await db.commit()
    return JSONResponse(result.resultado,status_code=result.status_code,headers={'Cache-Control':'no-store'})


@router.post('/{template_id}/configuracion')
async def cambiar_configuracion_aplicacion(template_id:int,data:RevisarAplicacion,clave:str=Header(alias='Idempotency-Key'),
        current_user:Usuario=Depends(require_admin),db:AsyncSession=Depends(get_db)):
    from app.services.configuracion_despliegue_service import change
    result=await change(db,actor=current_user,body=data,clave=clave,template_id=template_id)
    await db.commit()
    return JSONResponse(result.resultado,status_code=result.status_code,headers={'Cache-Control':'no-store'})


@router.get("/", response_model=list[TemplateResponse])
async def listar_templates(
    incluir_retiradas: bool = False,
    modelo_servicio: Literal['iaas', 'paas', 'saas'] | None = None,
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Lista el catálogo de plantillas.

    Por defecto solo las activas: es el catálogo que la cátedra puede pedir.
    `incluir_retiradas` las trae todas, y es lo que le permite al administrador
    encontrar una plantilla que retiró para volver a habilitarla. Sin eso, retirar
    sería un camino de ida desde la interfaz.
    `modelo_servicio` permite filtrar plantillas por iaas, paas o saas.
    """
    consulta = select(RecursoTemplate)
    if not (incluir_retiradas and current_user.rol == RolUsuario.ADMIN):
        consulta = consulta.where(RecursoTemplate.activo == True)
    if modelo_servicio:
        consulta = consulta.where(RecursoTemplate.modelo_servicio == modelo_servicio.lower())
    result = await db.execute(consulta)
    templates = await anexar_disponibilidad(db, list(result.scalars().all()))
    if current_user.rol != RolUsuario.ADMIN:
        templates = [row for row in templates if row.oferta_disponible]
    return [_presentar(row, current_user) for row in templates]


def _presentar(template, user):
    response = TemplateResponse.model_validate(template)
    if user.rol != RolUsuario.ADMIN:
        response.os_template = None
        response.config_extra = None
    return response


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
    await anexar_disponibilidad(db, [template])
    if current_user.rol != RolUsuario.ADMIN and not template.oferta_disponible:
        from app.services.acceso_service import catedras_visibles
        visible = await catedras_visibles(db, current_user)
        requested = await db.scalar(select(Pedido.id).where(Pedido.template_id == template.id,
            Pedido.catedra_id.in_(visible)).limit(1))
        delivered = await db.scalar(select(Servicio.id).where(Servicio.template_id == template.id,
            Servicio.catedra_id.in_(visible)).limit(1))
        if not requested and not delivered:
            raise error(403, 'sin_permisos', 'La plantilla histórica no está disponible para esta cátedra')
    return _presentar(template, current_user)


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

    modelo_enum = ModeloServicio.IAAS
    if data.modelo_servicio:
        try:
            modelo_enum = ModeloServicio(data.modelo_servicio.lower())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Modelo de servicio inválido: {data.modelo_servicio}. Debe ser iaas, paas o saas",
            )

    template = RecursoTemplate(
        nombre=data.nombre,
        descripcion=data.descripcion,
        modelo_servicio=modelo_enum,
        tipo=TipoRecurso(data.tipo),
        default_vcpus=data.default_vcpus,
        default_ram_mb=data.default_ram_mb,
        default_disk_gb=data.default_disk_gb,
        justificacion_disco=data.justificacion_disco,
        os_template=data.os_template,
        config_extra=data.config_extra,
        definicion_version_id=data.definicion_version_id,
        activo=True,
    )
    await exigir_definicion(db, template, bloquear=True)
    db.add(template)
    await db.commit()
    await db.refresh(template)

    await anexar_disponibilidad(db, [template])
    return _presentar(template, current_user)


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
    template = await db.scalar(select(RecursoTemplate).where(RecursoTemplate.id == template_id)
        .with_for_update().execution_options(populate_existing=True))
    if not template:
        raise HTTPException(status_code=404, detail="Template no encontrado")

    cambios = data.model_dump(exclude_unset=True)
    tamano = cambios.pop('tamano', None)
    if tamano:
        try:
            validar_tamano(tamano, {key: cambios.get('default_' + key, getattr(template, 'default_' + key))
                                   for key in ['vcpus', 'ram_mb', 'disk_gb']})
        except ValueError as exc:
            raise error(422, 'tamano_incompatible', str(exc)) from None
    if template.tipo == TipoRecurso.QEMU and cambios != {'activo': False}:
        raise error(422, 'tipo_historico', 'La plantilla QEMU histórica admite lectura o retiro')

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

    if "modelo_servicio" in cambios and cambios["modelo_servicio"]:
        try:
            cambios["modelo_servicio"] = ModeloServicio(cambios["modelo_servicio"].lower())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Modelo de servicio inválido: {cambios['modelo_servicio']}",
            )

    relevant = {'definicion_version_id', 'default_vcpus', 'default_ram_mb', 'default_disk_gb',
        'modelo_servicio', 'os_template', 'config_extra', 'activo', 'configuracion_despliegue_id'}
    prospective = SimpleNamespace(**{**{field: getattr(template, field) for field in relevant | {'tipo'}}, **cambios})
    if prospective.activo and (template.definicion_version_id or relevant & cambios.keys()):
        await exigir_definicion(db, prospective, bloquear=True)
    for campo, valor in cambios.items():
        setattr(template, campo, valor)

    if cambios:
        template.revision += 1

    await db.commit()
    await db.refresh(template)
    await anexar_disponibilidad(db, [template])
    respuesta = _presentar(template, current_user)
    respuesta.alcance_del_cambio = await _alcance_del_cambio(db, template_id)
    return respuesta


@router.delete("/{template_id}", response_model=TemplateResponse)
async def desactivar_template(
    template_id: int,
    current_user: Usuario = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Desactiva (soft-delete / retira) una plantilla del catálogo. Solo administradores."""
    template = await db.scalar(select(RecursoTemplate).where(RecursoTemplate.id == template_id)
        .with_for_update().execution_options(populate_existing=True))
    if not template:
        raise HTTPException(status_code=404, detail="Template no encontrado")

    template.activo = False
    template.revision += 1
    await db.commit()
    await db.refresh(template)
    await anexar_disponibilidad(db, [template])
    respuesta = _presentar(template, current_user)
    respuesta.alcance_del_cambio = await _alcance_del_cambio(db, template_id)
    return respuesta
