from app.services.acceso_service import requiere_admin_actual
"""Servicio de negocio para gestión de pedidos con máquina de estados."""

from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from fastapi import HTTPException, status

from app.models.pedido import (
    Pedido,
    PedidoHistorial,
    EstadoPedido,
    TipoPedido,
    ModeloServicio,
    VigenciaTipo,
)
from app.models.catedra import Catedra
from app.models.usuario import Usuario, RolUsuario
from app.models.recurso_template import RecursoTemplate
from app.models.servicio import Servicio, EstadoServicio
from app.services import capacidad_service, historial_service
from app.services.acceso_service import catedras_visibles


# ===== Máquina de Estados =====
# Define las transiciones válidas: estado_actual → [estados_posibles]
TRANSICIONES_VALIDAS: dict[EstadoPedido, list[EstadoPedido]] = {
    EstadoPedido.SOLICITADO: [
        EstadoPedido.CANCELADO,
        EstadoPedido.APROBADO,
        EstadoPedido.RECHAZADO,
        EstadoPedido.REQUIERE_AJUSTE,
    ],
    EstadoPedido.REQUIERE_AJUSTE: [
        EstadoPedido.SOLICITADO,
        EstadoPedido.CANCELADO,
        EstadoPedido.RECHAZADO,
    ],
    EstadoPedido.CANCELADO: [],  # Estado final
    # APROBADO → RECHAZADO la ejecuta el sistema cuando vence la reserva de
    # capacidad sin que el despliegue se haya concretado. Sin esta transición,
    # ese trabajo periódico no tendría forma legítima de cambiar el estado y la
    # capacidad quedaría comprometida para siempre.
    EstadoPedido.APROBADO: [EstadoPedido.EN_DESPLIEGUE, EstadoPedido.RECHAZADO, EstadoPedido.REQUIERE_AJUSTE],
    EstadoPedido.EN_DESPLIEGUE: [EstadoPedido.ACTIVO, EstadoPedido.ERROR, EstadoPedido.RECHAZADO, EstadoPedido.REQUIERE_AJUSTE],
    EstadoPedido.ACTIVO: [EstadoPedido.SUSPENDIDO],
    EstadoPedido.ERROR: [EstadoPedido.EN_DESPLIEGUE, EstadoPedido.RECHAZADO],
    EstadoPedido.SUSPENDIDO: [EstadoPedido.ACTIVO],
    EstadoPedido.RECHAZADO: [],  # Estado final
}

# Estados que solo un admin puede ejecutar
TRANSICIONES_ADMIN = {
    EstadoPedido.APROBADO,
    EstadoPedido.RECHAZADO,
    EstadoPedido.REQUIERE_AJUSTE,
    EstadoPedido.EN_DESPLIEGUE,
    EstadoPedido.ACTIVO,
    EstadoPedido.ERROR,
    EstadoPedido.SUSPENDIDO,
}

# Transiciones que solo puede ejecutar el orquestador (orquestacion_service),
# nunca un cambio de estado manual vía API: son el reflejo de un despliegue
# real contra Proxmox, no una decisión administrativa. Sin este freno, marcar
# un pedido como EN_DESPLIEGUE o ACTIVO a mano lo dejaba en un estado
# "desplegado" sin ningún Servicio ni contenedor detrás.
TRANSICIONES_SISTEMA: set[tuple[EstadoPedido, EstadoPedido]] = {
    (EstadoPedido.APROBADO, EstadoPedido.EN_DESPLIEGUE),
    (EstadoPedido.EN_DESPLIEGUE, EstadoPedido.ACTIVO),
    (EstadoPedido.EN_DESPLIEGUE, EstadoPedido.ERROR),
    (EstadoPedido.ERROR, EstadoPedido.EN_DESPLIEGUE),
    # Expiración de la reserva de capacidad, y su equivalente humano: la
    # reversión de una aprobación. Estar acá ya no significa "solo el sistema"
    # sino **"no se alcanza cambiando el estado a mano"**: el peligro nunca fue
    # que una persona decidiera revertir, sino que alguien moviera el estado sin
    # liberar la reserva y dejara capacidad huérfana. Por eso la reversión entra
    # por una operación con nombre propio, que hace las dos cosas juntas (R1).
    (EstadoPedido.APROBADO, EstadoPedido.RECHAZADO),
    (EstadoPedido.APROBADO, EstadoPedido.REQUIERE_AJUSTE),
    (EstadoPedido.EN_DESPLIEGUE, EstadoPedido.RECHAZADO),
    (EstadoPedido.EN_DESPLIEGUE, EstadoPedido.REQUIERE_AJUSTE),
}


def validar_transicion(estado_actual: EstadoPedido, estado_nuevo: EstadoPedido) -> bool:
    """Valida si una transición de estado es permitida."""
    destinos = TRANSICIONES_VALIDAS.get(estado_actual, [])
    return estado_nuevo in destinos


async def transicionar(db, pedido_id, nuevo_estado, *, usuario=None, motivo,
                       operacion_id=None, evento_clave=None, metadata=None):
    """Única asignación de estado existente; no confirma la transacción."""
    pedido = await db.scalar(select(Pedido).where(Pedido.id == pedido_id).with_for_update()
                             .execution_options(populate_existing=True))
    if pedido is None:
        raise HTTPException(status_code=404, detail='Pedido no encontrado')
    nuevo_estado = EstadoPedido(nuevo_estado)
    if evento_clave:
        previous = await db.scalar(select(PedidoHistorial).where(
            PedidoHistorial.pedido_id == pedido.id, PedidoHistorial.evento_clave == evento_clave))
        if previous:
            if (previous.estado_nuevo != nuevo_estado.value
                or previous.usuario_id != (usuario.id if usuario else None)
                or previous.comentario != motivo or previous.operacion_id != operacion_id):
                raise HTTPException(status_code=409, detail='La clave histórica corresponde a otro evento')
            return pedido
    if not motivo or not motivo.strip():
        raise HTTPException(status_code=422, detail='La transición requiere un motivo')
    if not validar_transicion(pedido.estado, nuevo_estado):
        raise HTTPException(status_code=409,
                            detail=f'Transición inválida: {pedido.estado.value} → {nuevo_estado.value}')
    anterior = pedido.estado.value
    pedido.estado = nuevo_estado
    pedido.updated_at = datetime.utcnow()
    pedido.revision += 1
    if nuevo_estado in {EstadoPedido.ACTIVO, EstadoPedido.RECHAZADO, EstadoPedido.CANCELADO}:
        pedido.resolved_at = pedido.updated_at
    db.add(historial_service.registrar_pedido(pedido.id, anterior, nuevo_estado.value,
        comentario=motivo, usuario=usuario, operacion_id=operacion_id,
        evento_clave=evento_clave, metadata=metadata))
    await db.flush()
    return pedido


async def crear_pedido(db, *, usuario, payload, clave):
    from app.services.solicitud_service import crear
    return await crear(db, actor=usuario, payload=payload, clave=clave)


async def aprobar_pedido(db, pedido_id, admin, *, seleccion, capacidad_token, clave,
    justificacion_capacidad=None, desplegar_inmediatamente=False):
    """La decisión usa la misma admisión durable que HTTP; sin overrides libres."""
    from app.services.admision_service import aprobar
    return await aprobar(db, pedido_id, actor=admin, clave=clave,
        payload={**seleccion, 'capacidad_token': capacidad_token,
                 'justificacion_capacidad': justificacion_capacidad,
                 'desplegar_inmediatamente': desplegar_inmediatamente})


async def rechazar_pedido(db, pedido_id, admin, motivo, *, clave):
    from app.services.solicitud_service import resolver
    return await resolver(db, pedido_id, actor=admin, tipo='rechazar', payload={'motivo': motivo}, clave=clave)


async def solicitar_ajuste(db, pedido_id, admin, observaciones, *, clave):
    from app.services.admision_service import ajustar
    return await ajustar(db, pedido_id, actor=admin, observaciones=observaciones, clave=clave)


async def reenviar_pedido(db, pedido_id, usuario, *, payload, clave):
    from app.services.solicitud_service import resolver
    return await resolver(db, pedido_id, actor=usuario, tipo='reenviar', payload=payload, clave=clave)


async def cancelar_pedido(db, pedido_id, usuario, motivo, *, clave):
    from app.services.solicitud_service import resolver
    return await resolver(db, pedido_id, actor=usuario, tipo='cancelar', payload={'motivo': motivo}, clave=clave)


# --- Reversión de una aprobación (feature 005) ------------------------------

# Estados en los que el aprovisionamiento ya tocó la infraestructura. Desde acá
# la vuelta atrás deja de ser una decisión administrativa y pasa a ser una baja
# de servicio, que tiene su propio camino y su propia liberación en Proxmox.
ESTADOS_CON_DESPLIEGUE = {
    EstadoPedido.EN_DESPLIEGUE,
    EstadoPedido.ACTIVO,
    EstadoPedido.SUSPENDIDO,
    EstadoPedido.ERROR,
}


async def _conflicto_de_reversion(db: AsyncSession, pedido: Pedido) -> HTTPException:
    """Nombra por qué este pedido no se puede revertir.

    Los cuatro casos comparten el código HTTP, pero para quien los recibe son
    situaciones distintas y cada una tiene una salida distinta. Un genérico
    "transición inválida" ante algo que el sistema hizo por su cuenta se lee
    como una falla del portal.
    """
    if pedido.estado in ESTADOS_CON_DESPLIEGUE:
        return HTTPException(
            status_code=409,
            detail={
                "codigo": "despliegue_en_curso",
                "mensaje": (
                    "El servicio ya se está creando o ya existe. Para deshacerlo hay "
                    "que dar de baja el servicio, no la aprobación."
                ),
                "estado_actual": pedido.estado.value,
            },
        )

    if pedido.estado == EstadoPedido.RECHAZADO:
        # Vencimiento y reversión llegan al mismo estado desde el mismo estado
        # anterior; lo que los separa es el autor de esa transición (R6).
        ultima = (
            await db.execute(
                select(PedidoHistorial)
                .where(
                    PedidoHistorial.pedido_id == pedido.id,
                    PedidoHistorial.estado_nuevo == EstadoPedido.RECHAZADO.value,
                    PedidoHistorial.estado_anterior == EstadoPedido.APROBADO.value,
                )
                .order_by(PedidoHistorial.id.desc())
                .limit(1)
            )
        ).scalars().first()

        if ultima is not None and ultima.usuario_id is None:
            return HTTPException(
                status_code=409,
                detail={
                    "codigo": "reserva_ya_vencida",
                    "mensaje": (
                        "La reserva de este pedido ya se liberó sola porque el "
                        "despliegue nunca se concretó. No hay capacidad que recuperar."
                    ),
                },
            )
        if ultima is not None:
            return HTTPException(
                status_code=409,
                detail={
                    "codigo": "ya_revertido",
                    "mensaje": (
                        "Otra persona revirtió esta aprobación recién. La capacidad "
                        "ya está liberada."
                    ),
                },
            )

    return HTTPException(
        status_code=409,
        detail={
            "codigo": "pedido_no_aprobado",
            "mensaje": (
                "Este pedido no tiene ninguna aprobación que deshacer. Si querés que "
                "no avance, rechazalo."
            ),
            "estado_actual": pedido.estado.value,
        },
    )


async def revertir_aprobacion(db, pedido_id, admin, motivo, *, clave):
    from app.services.admision_service import liberar
    if not motivo or not motivo.strip():
        raise HTTPException(status_code=422, detail='Indicá el motivo de la reversión')
    return await liberar(db, pedido_id, actor=admin, motivo='Aprobación revertida: ' + motivo.strip(), clave=clave)


async def transicion_del_sistema(
    db: AsyncSession,
    pedido: Pedido,
    nuevo_estado: EstadoPedido,
    comentario: str,
) -> Pedido:
    """Transición ejecutada por el sistema, sin persona detrás.

    Queda registrada en el historial con autor nulo, que es como se representa
    al sistema. No se atribuye a nadie ni se omite del historial.
    """
    return await transicionar(db, pedido.id, nuevo_estado, motivo=comentario)


async def dar_de_baja_pedido(db, pedido_id, admin, *, clave):
    from app.services.admision_service import dar_de_baja
    return await dar_de_baja(db, pedido_id, actor=admin, clave=clave)


async def cambiar_estado(
    db: AsyncSession,
    pedido_id: int,
    nuevo_estado_str: str,
    usuario: Usuario,
    comentario: str | None = None,
    motivo_rechazo: str | None = None,
    origen_sistema: bool = False,
    operacion_nombrada: bool = False,
) -> Pedido:
    """
    Cambia el estado de un pedido siguiendo la máquina de estados.

    `origen_sistema` lo pasa en `True` únicamente `orquestacion_service`, al
    reflejar el resultado de un despliegue real. El endpoint público de cambio
    de estado nunca lo setea, así que un admin no puede simular a mano que un
    pedido "se desplegó" sin que haya un `Servicio` real detrás.

    `operacion_nombrada` lo pasa en `True` una operación que hace la transición
    **junto con** todo lo que esa transición implica —hoy solo
    `revertir_aprobacion`, que además libera la reserva—. La diferencia con
    `origen_sistema` importa: el autor sigue siendo la persona que ejecutó la
    operación, así que el historial no atribuye al sistema una decisión humana.
    El endpoint público tampoco lo setea nunca.
    """
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

    # Transiciones de sistema: solo el orquestador puede ejecutarlas
    if (
        (pedido.estado, nuevo_estado) in TRANSICIONES_SISTEMA
        and not origen_sistema
        and not operacion_nombrada
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                f"La transición {pedido.estado.value} → {nuevo_estado_str} la ejecuta "
                "el sistema durante el despliegue. Usá el endpoint de despliegue "
                "o reintento en lugar de cambiar el estado a mano."
            ),
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

    if motivo_rechazo:
        pedido.motivo_rechazo = motivo_rechazo
    pedido = await transicionar(db, pedido.id, nuevo_estado, usuario=usuario,
        motivo=comentario or motivo_rechazo or f'Pedido {nuevo_estado.value}')
    await db.commit()
    await db.refresh(pedido)

    return pedido
