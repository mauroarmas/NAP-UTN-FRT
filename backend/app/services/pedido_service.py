"""Servicio de negocio para gestión de pedidos con máquina de estados."""

from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from fastapi import HTTPException, status

from app.models.pedido import Pedido, PedidoHistorial, EstadoPedido, TipoPedido
from app.models.catedra import Catedra
from app.models.usuario import Usuario, RolUsuario
from app.models.recurso_template import RecursoTemplate
from app.models.servicio import Servicio, EstadoServicio
from app.services import capacidad_service, historial_service
from app.services.acceso_service import catedras_visibles
from app.services.limites_service import validar_disco_template


# ===== Máquina de Estados =====
# Define las transiciones válidas: estado_actual → [estados_posibles]
TRANSICIONES_VALIDAS: dict[EstadoPedido, list[EstadoPedido]] = {
    EstadoPedido.SOLICITADO: [EstadoPedido.APROBADO, EstadoPedido.RECHAZADO],
    # APROBADO → RECHAZADO la ejecuta el sistema cuando vence la reserva de
    # capacidad sin que el despliegue se haya concretado. Sin esta transición,
    # ese trabajo periódico no tendría forma legítima de cambiar el estado y la
    # capacidad quedaría comprometida para siempre.
    EstadoPedido.APROBADO: [EstadoPedido.EN_DESPLIEGUE, EstadoPedido.RECHAZADO],
    EstadoPedido.EN_DESPLIEGUE: [EstadoPedido.ACTIVO, EstadoPedido.ERROR],
    EstadoPedido.ACTIVO: [EstadoPedido.SUSPENDIDO],
    EstadoPedido.ERROR: [EstadoPedido.EN_DESPLIEGUE, EstadoPedido.RECHAZADO],
    EstadoPedido.SUSPENDIDO: [EstadoPedido.ACTIVO],
    EstadoPedido.RECHAZADO: [],  # Estado final
}

# Estados que solo un admin puede ejecutar
TRANSICIONES_ADMIN = {
    EstadoPedido.APROBADO,
    EstadoPedido.RECHAZADO,
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
}


def validar_transicion(estado_actual: EstadoPedido, estado_nuevo: EstadoPedido) -> bool:
    """Valida si una transición de estado es permitida."""
    destinos = TRANSICIONES_VALIDAS.get(estado_actual, [])
    return estado_nuevo in destinos


async def crear_pedido(
    db: AsyncSession,
    template_id: int,
    usuario: Usuario,
    catedra_id: int | None = None,
    parametros_extra: dict | None = None,
) -> Pedido:
    """Crea un pedido de servicio.

    Ya no se verifica consumo acumulado: la cátedra no tiene un techo declarado
    por adelantado, así que ningún pedido bien formado se rechaza por esa razón.
    Quién decide es el administrador al aprobarlo, con la capacidad real a la
    vista.
    """
    visibles = await catedras_visibles(db, usuario)
    if not visibles:
        raise HTTPException(
            status_code=400,
            detail="No tenés ninguna cátedra asignada; pedile a un administrador que te asigne una",
        )

    if catedra_id is None:
        if len(visibles) > 1:
            raise HTTPException(
                status_code=400,
                detail="Indicá para cuál de tus cátedras es el pedido",
            )
        catedra_id = next(iter(visibles))
    elif catedra_id not in visibles:
        raise HTTPException(
            status_code=403,
            detail="No podés crear pedidos a nombre de una cátedra que no es tuya",
        )

    template = await db.get(RecursoTemplate, template_id)
    if not template or not template.activo:
        raise HTTPException(status_code=404, detail="Template no encontrado o inactivo")

    # Tope de disco por contenedor: es un límite por recurso, no una cuota.
    validar_disco_template(template)

    pedido = Pedido(
        catedra_id=catedra_id,
        solicitante_id=usuario.id,
        template_id=template_id,
        estado=EstadoPedido.SOLICITADO,
        tipo=TipoPedido.ALTA,
        parametros_extra=parametros_extra,
    )

    db.add(pedido)
    await db.flush()

    db.add(
        historial_service.registrar_pedido(
            pedido.id,
            "nuevo",
            EstadoPedido.SOLICITADO.value,
            comentario="Pedido creado",
            usuario=usuario,
        )
    )
    await db.commit()
    await db.refresh(pedido)

    return pedido


async def aprobar_pedido(
    db: AsyncSession,
    pedido_id: int,
    admin: Usuario,
    capacidad_token: str | None = None,
    justificacion_capacidad: str | None = None,
) -> Pedido:
    """Aprueba un pedido y **reserva** la capacidad correspondiente.

    La verificación y la reserva ocurren dentro del mismo bloqueo y la misma
    transacción. Sin eso, dos aprobaciones consecutivas pueden comprometer la
    misma capacidad libre y sobrecomprometer el clúster sin que nadie cometa un
    error individual: cada decisión sería correcta contra los números que vio.
    """
    pedido = await db.get(Pedido, pedido_id)
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    if pedido.estado != EstadoPedido.SOLICITADO:
        raise HTTPException(
            status_code=409,
            detail=f"Solo se aprueban pedidos en estado solicitado (está en '{pedido.estado.value}')",
        )

    template = await db.get(RecursoTemplate, pedido.template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template no encontrado")

    async with capacidad_service.bloqueo_capacidad(db):
        estado = await capacidad_service.panorama(db)

        # El token detecta que se está confirmando sobre números viejos.
        if capacidad_token and capacidad_token != estado["capacidad_token"]:
            raise HTTPException(
                status_code=409,
                detail={
                    "codigo": "token_desactualizado",
                    "mensaje": (
                        "La capacidad del clúster cambió desde que se mostraron estos "
                        "números. Revisá los valores vigentes y confirmá de nuevo."
                    ),
                    "capacidad": estado,
                },
            )

        if pedido.tipo == TipoPedido.RENOVACION:
            # Una renovación no reserva: el servicio ya está desplegado y ya
            # cuenta como consumo. Contarlo otra vez sería contabilidad doble.
            costo = {"vcpus": 0, "ram_mb": 0, "storage_gb": 0}
        else:
            costo = capacidad_service.costo_de(template)

        if capacidad_service.excede(estado["libre"], costo) and not (
            justificacion_capacidad and justificacion_capacidad.strip()
        ):
            raise HTTPException(
                status_code=400,
                detail={
                    "codigo": "excede_capacidad",
                    "mensaje": (
                        "Aprobar este pedido compromete más capacidad de la disponible. "
                        "Podés hacerlo igual, pero necesitás dejar una justificación."
                    ),
                    "capacidad": estado,
                    "costo": costo,
                },
            )

        pedido.reserva_vcpus = costo["vcpus"]
        pedido.reserva_ram_mb = costo["ram_mb"]
        pedido.reserva_disk_gb = costo["storage_gb"]
        pedido.reserva_expira_at = (
            datetime.utcnow() + capacidad_service.RESERVA_VIGENCIA
        )
        pedido.justificacion_capacidad = justificacion_capacidad
        pedido.estado = EstadoPedido.APROBADO
        pedido.updated_at = datetime.utcnow()

        comentario = "Pedido aprobado"
        if justificacion_capacidad:
            comentario += f" por encima de la capacidad libre: {justificacion_capacidad}"
        db.add(
            historial_service.registrar_pedido(
                pedido.id,
                EstadoPedido.SOLICITADO.value,
                EstadoPedido.APROBADO.value,
                comentario=comentario,
                usuario=admin,
            )
        )
        await db.commit()

    await db.refresh(pedido)
    return pedido


async def rechazar_pedido(
    db: AsyncSession, pedido_id: int, admin: Usuario, motivo: str
) -> Pedido:
    """Rechaza un pedido. El motivo es obligatorio y lo ve la cátedra."""
    if not motivo or not motivo.strip():
        raise HTTPException(status_code=400, detail="Se requiere un motivo de rechazo")
    return await cambiar_estado(
        db, pedido_id, EstadoPedido.RECHAZADO.value, admin, motivo_rechazo=motivo
    )


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


async def revertir_aprobacion(
    db: AsyncSession, pedido_id: int, admin: Usuario, motivo: str | None
) -> tuple[Pedido, dict]:
    """Deshace una aprobación antes del despliegue y libera su reserva.

    Es la mitad que le faltaba a la feature 004: aprobar compromete capacidad en
    el acto, y hasta acá lo único que la soltaba era desplegar el pedido o
    esperar 24 h al vencimiento automático. Durante esa ventana el error de una
    cátedra degradaba el servicio de las demás.

    Todo ocurre dentro del bloqueo de capacidad y de una sola transacción. Las
    dos cosas importan y por razones distintas:

    - El **bloqueo** serializa, y la **relectura del estado adentro** es lo que
      impide la doble liberación: la segunda reversión encuentra el pedido ya
      fuera de APROBADO. Sin releer, dos reversiones podrían pasar el chequeo
      antes de que ninguna escribiera y liberar dos veces (FR-005).
    - La **transacción única** hace indivisible la liberación y el cambio de
      estado. El estado intermedio —capacidad soltada sobre un pedido que sigue
      aprobado— sería peor que el defecto original: el saldo libre contaría como
      disponible algo que en realidad está comprometido (FR-004, I3).

    No hace falta `capacidad_token`: el token protege contra *decidir* sobre un
    saldo viejo, y acá no hay decisión contra el saldo — se libera.
    """
    if not motivo or not motivo.strip():
        raise HTTPException(
            status_code=400,
            detail="Se requiere un motivo para revertir la aprobación",
        )
    motivo = motivo.strip()

    async with capacidad_service.bloqueo_capacidad(db):
        # `populate_existing` fuerza la lectura contra la base en lugar de
        # devolver lo que la sesión ya tenía cargado. Es justamente el caso de
        # dos reversiones simultáneas: la segunda leyó el pedido aprobado antes
        # de que la primera escribiera.
        pedido = (
            await db.execute(
                select(Pedido)
                .where(Pedido.id == pedido_id, Pedido.deleted_at.is_(None))
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()

        if pedido is None:
            raise HTTPException(status_code=404, detail="Pedido no encontrado")

        if pedido.estado != EstadoPedido.APROBADO:
            raise await _conflicto_de_reversion(db, pedido)

        try:
            liberado = capacidad_service.liberar_reserva(pedido)
            texto = f"Aprobación revertida: {motivo}"
            # `motivo_rechazo` nombra la situación para que la cátedra no lea un
            # "rechazado" a secas. `justificacion_capacidad` no se toca: es parte
            # del registro de la aprobación que se está deshaciendo, y borrarla
            # perdería la mitad de la historia.
            await cambiar_estado(
                db,
                pedido_id,
                EstadoPedido.RECHAZADO.value,
                admin,
                comentario=texto,
                motivo_rechazo=texto,
                operacion_nombrada=True,
            )
        except Exception:
            # La atomicidad no se delega al cierre de la sesión: si algo falla a
            # mitad de camino, acá mismo queda deshecha la liberación.
            await db.rollback()
            raise

    await db.refresh(pedido)
    return pedido, liberado


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
    if not validar_transicion(pedido.estado, nuevo_estado):
        raise HTTPException(
            status_code=409,
            detail=f"Transición inválida: {pedido.estado.value} → {nuevo_estado.value}",
        )

    anterior = pedido.estado.value
    pedido.estado = nuevo_estado
    pedido.updated_at = datetime.utcnow()
    if nuevo_estado in (EstadoPedido.ACTIVO, EstadoPedido.RECHAZADO):
        pedido.resolved_at = datetime.utcnow()

    db.add(
        historial_service.registrar_pedido(
            pedido.id, anterior, nuevo_estado.value, comentario=comentario, usuario=None
        )
    )
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
