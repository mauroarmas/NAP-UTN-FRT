"""Servicio de negocio para gestión de pedidos con máquina de estados."""

from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from fastapi import HTTPException, status

from app.models.pedido import Pedido, PedidoHistorial, EstadoPedido
from app.models.catedra import Catedra
from app.models.usuario import Usuario, RolUsuario
from app.models.recurso_template import RecursoTemplate
from app.models.servicio import Servicio, EstadoServicio


# ===== Máquina de Estados =====
# Define las transiciones válidas: estado_actual → [estados_posibles]
TRANSICIONES_VALIDAS: dict[EstadoPedido, list[EstadoPedido]] = {
    EstadoPedido.SOLICITADO: [EstadoPedido.EN_REVISION, EstadoPedido.RECHAZADO],
    EstadoPedido.EN_REVISION: [EstadoPedido.APROBADO, EstadoPedido.RECHAZADO],
    EstadoPedido.APROBADO: [EstadoPedido.EN_DESPLIEGUE],
    EstadoPedido.EN_DESPLIEGUE: [EstadoPedido.ACTIVO, EstadoPedido.ERROR],
    EstadoPedido.ACTIVO: [EstadoPedido.SUSPENDIDO],
    EstadoPedido.ERROR: [EstadoPedido.EN_DESPLIEGUE, EstadoPedido.RECHAZADO],
    EstadoPedido.SUSPENDIDO: [EstadoPedido.ACTIVO],
    EstadoPedido.RECHAZADO: [],  # Estado final
}

# Estados que solo un admin puede ejecutar
TRANSICIONES_ADMIN = {
    EstadoPedido.EN_REVISION,
    EstadoPedido.APROBADO,
    EstadoPedido.RECHAZADO,
    EstadoPedido.EN_DESPLIEGUE,
    EstadoPedido.ACTIVO,
    EstadoPedido.ERROR,
    EstadoPedido.SUSPENDIDO,
}


def validar_transicion(estado_actual: EstadoPedido, estado_nuevo: EstadoPedido) -> bool:
    """Valida si una transición de estado es permitida."""
    destinos = TRANSICIONES_VALIDAS.get(estado_actual, [])
    return estado_nuevo in destinos


async def verificar_cuota(
    db: AsyncSession, catedra_id: int, template: RecursoTemplate
) -> dict:
    """Verifica si la cátedra tiene cuota disponible para el recurso solicitado."""
    catedra = await db.get(Catedra, catedra_id)
    if not catedra:
        raise HTTPException(status_code=404, detail="Cátedra no encontrada")

    # Calcular uso actual de la cátedra (servicios activos/running)
    result = await db.execute(
        select(
            func.coalesce(func.sum(Servicio.vcpus_asignados), 0),
            func.coalesce(func.sum(Servicio.ram_asignada_mb), 0),
            func.coalesce(func.sum(Servicio.disk_asignado_gb), 0),
        ).where(
            Servicio.catedra_id == catedra_id,
            Servicio.estado == EstadoServicio.RUNNING,
            # Lo dado de baja no ocupa cuota (FR-012)
            Servicio.deleted_at.is_(None),
        )
    )
    uso_vcpus, uso_ram, uso_disk = result.one()

    # Verificar contra cuotas
    disponible_vcpus = catedra.cuota_vcpus - uso_vcpus
    disponible_ram = catedra.cuota_ram_mb - uso_ram
    disponible_disk = catedra.cuota_storage_gb - uso_disk

    excedido = []
    if template.default_vcpus > disponible_vcpus:
        excedido.append(f"vCPUs: necesita {template.default_vcpus}, disponible {disponible_vcpus}")
    if template.default_ram_mb > disponible_ram:
        excedido.append(f"RAM: necesita {template.default_ram_mb}MB, disponible {disponible_ram}MB")
    if template.default_disk_gb > disponible_disk:
        excedido.append(f"Disco: necesita {template.default_disk_gb}GB, disponible {disponible_disk}GB")

    return {
        "dentro_de_cuota": len(excedido) == 0,
        "excedido": excedido,
        "uso_actual": {"vcpus": uso_vcpus, "ram_mb": uso_ram, "disk_gb": uso_disk},
        "cuota_total": {
            "vcpus": catedra.cuota_vcpus,
            "ram_mb": catedra.cuota_ram_mb,
            "disk_gb": catedra.cuota_storage_gb,
        },
    }


async def crear_pedido(
    db: AsyncSession,
    template_id: int,
    usuario: Usuario,
    parametros_extra: dict | None = None,
) -> Pedido:
    """Crea un nuevo pedido de servicio."""
    if not usuario.catedra_id:
        raise HTTPException(
            status_code=400,
            detail="El usuario no está asignado a ninguna cátedra",
        )

    # Verificar que el template existe y está activo
    template = await db.get(RecursoTemplate, template_id)
    if not template or not template.activo:
        raise HTTPException(status_code=404, detail="Template no encontrado o inactivo")

    # Verificar cuota antes de crear
    cuota = await verificar_cuota(db, usuario.catedra_id, template)
    if not cuota["dentro_de_cuota"]:
        raise HTTPException(
            status_code=409,
            detail=f"Cuota excedida: {', '.join(cuota['excedido'])}",
        )

    pedido = Pedido(
        catedra_id=usuario.catedra_id,
        solicitante_id=usuario.id,
        template_id=template_id,
        estado=EstadoPedido.SOLICITADO,
        parametros_extra=parametros_extra,
    )

    db.add(pedido)
    await db.flush()

    # Registrar en historial
    historial = PedidoHistorial(
        pedido_id=pedido.id,
        estado_anterior="nuevo",
        estado_nuevo=EstadoPedido.SOLICITADO.value,
        comentario="Pedido creado",
        usuario_id=usuario.id,
    )
    db.add(historial)
    await db.commit()
    await db.refresh(pedido)

    return pedido


async def dar_de_baja_pedido(
    db: AsyncSession,
    pedido_id: int,
    admin: Usuario,
) -> dict:
    """
    Da de baja lógicamente un pedido, cualquiera sea su estado (FR-013).

    Se rechaza si el pedido todavía tiene un servicio vigente: primero hay que
    darlo de baja para liberar el recurso real en la infraestructura, de modo
    que no queden contenedores huérfanos sin registro operativo (FR-014).
    """
    pedido = await db.get(Pedido, pedido_id)
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")

    if pedido.deleted_at is not None:
        return {
            "message": f"El pedido {pedido_id} ya estaba dado de baja",
            "deleted_at": pedido.deleted_at,
        }

    servicio_vigente = (
        await db.execute(
            select(Servicio).where(
                Servicio.pedido_id == pedido_id,
                Servicio.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()

    if servicio_vigente is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"El pedido tiene un servicio vigente (id={servicio_vigente.id}). "
                "Dé de baja el servicio primero para liberar el recurso."
            ),
        )

    pedido.deleted_at = datetime.utcnow()
    await db.commit()

    return {
        "message": f"Pedido {pedido_id} dado de baja",
        "deleted_at": pedido.deleted_at,
    }


async def cambiar_estado(
    db: AsyncSession,
    pedido_id: int,
    nuevo_estado_str: str,
    usuario: Usuario,
    comentario: str | None = None,
    motivo_rechazo: str | None = None,
) -> Pedido:
    """Cambia el estado de un pedido siguiendo la máquina de estados."""
    # Buscar pedido
    pedido = await db.get(Pedido, pedido_id)
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")

    # Parsear nuevo estado
    try:
        nuevo_estado = EstadoPedido(nuevo_estado_str)
    except ValueError:
        estados_validos = [e.value for e in EstadoPedido]
        raise HTTPException(
            status_code=400,
            detail=f"Estado inválido '{nuevo_estado_str}'. Válidos: {estados_validos}",
        )

    # Validar transición
    if not validar_transicion(pedido.estado, nuevo_estado):
        destinos = [e.value for e in TRANSICIONES_VALIDAS.get(pedido.estado, [])]
        raise HTTPException(
            status_code=409,
            detail=f"Transición inválida: {pedido.estado.value} → {nuevo_estado_str}. "
                   f"Transiciones válidas desde '{pedido.estado.value}': {destinos}",
        )

    # Verificar permisos (solo admin puede hacer la mayoría de transiciones)
    if nuevo_estado in TRANSICIONES_ADMIN and usuario.rol != RolUsuario.ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Solo un administrador puede realizar esta transición",
        )

    # Si es rechazo, requiere motivo
    if nuevo_estado == EstadoPedido.RECHAZADO and not motivo_rechazo:
        raise HTTPException(
            status_code=400, detail="Se requiere un motivo de rechazo"
        )

    # Guardar estado anterior
    estado_anterior = pedido.estado.value

    # Actualizar pedido
    pedido.estado = nuevo_estado
    pedido.updated_at = datetime.utcnow()

    if motivo_rechazo:
        pedido.motivo_rechazo = motivo_rechazo

    # Marcar resolved_at para estados finales
    if nuevo_estado in (EstadoPedido.ACTIVO, EstadoPedido.RECHAZADO):
        pedido.resolved_at = datetime.utcnow()

    # Registrar en historial
    historial = PedidoHistorial(
        pedido_id=pedido.id,
        estado_anterior=estado_anterior,
        estado_nuevo=nuevo_estado.value,
        comentario=comentario or motivo_rechazo,
        usuario_id=usuario.id,
    )
    db.add(historial)
    await db.commit()
    await db.refresh(pedido)

    return pedido
