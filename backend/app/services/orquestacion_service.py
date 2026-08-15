"""Servicio de orquestación: despliega y gestiona recursos reales en Proxmox VE."""

import asyncio
import logging
import secrets
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException

from app.models.pedido import Pedido, PedidoHistorial, EstadoPedido
from app.models.servicio import Servicio, EstadoServicio
from app.models.recurso_template import RecursoTemplate, TipoRecurso
from app.models.usuario import Usuario, RolUsuario
from app.schemas.servicio import ConsolaTicketResponse
from app.services.proxmox_client import get_proxmox_client
from app.services.pedido_service import cambiar_estado

logger = logging.getLogger(__name__)

TICKET_CONSOLA_TTL_SEGUNDOS = 30

# Traducción del `status` que reporta Proxmox al estado que persiste el portal.
# Lo que Proxmox no sepa clasificar no se mapea: preferimos no tocar el registro
# antes que inventar un estado (ver `sincronizar_estados`).
_ESTADO_POR_STATUS_PROXMOX = {
    "running": EstadoServicio.RUNNING,
    "stopped": EstadoServicio.STOPPED,
    "paused": EstadoServicio.PAUSED,
    "suspended": EstadoServicio.PAUSED,
}

# Tickets de consola propios del portal: de un solo uso, corta vida, en memoria del
# proceso (no se persisten — ver data-model.md de la spec 003). ticket -> datos de
# conexión hacia Proxmox necesarios para el proxy de WebSocket.
_tickets_consola: dict[str, dict] = {}


def requiere_propio_o_admin(servicio: Servicio, usuario: Usuario) -> None:
    """
    Autorización de servicios: admin pasa siempre; cátedra solo sobre lo suyo.

    Centraliza el chequeo que antes estaba duplicado en cada endpoint de
    lectura (``obtener_servicio``, ``estado_en_proxmox``) y que las acciones
    de apagar/encender/reiniciar/consola multiplicarían si se siguiera
    duplicando.
    """
    if usuario.rol != RolUsuario.ADMIN and servicio.catedra_id != usuario.catedra_id:
        raise HTTPException(status_code=403, detail="Sin permisos")


def _estados_reales_del_cluster() -> dict[int, EstadoServicio] | None:
    """
    Estado real de cada LXC del clúster, indexado por VMID.

    Una sola llamada a `cluster/resources` cubre todos los nodos, así que
    reconciliar N servicios no cuesta N requests contra Proxmox.

    Devuelve ``None`` si Proxmox no responde (clúster apagado, red caída): en
    ese caso no se sabe nada del estado real y el portal conserva lo último
    conocido en lugar de marcar todo como caído.
    """
    try:
        recursos = get_proxmox_client().listar_lxc_del_cluster()
    except Exception as exc:
        logger.warning(f"No se pudo consultar el estado real de los contenedores: {exc}")
        return None

    estados: dict[int, EstadoServicio] = {}
    for recurso in recursos:
        vmid = recurso.get("vmid")
        estado = _ESTADO_POR_STATUS_PROXMOX.get(recurso.get("status"))
        if vmid is not None and estado is not None:
            estados[int(vmid)] = estado
    return estados


def _existe_en_el_cluster(pve, vmid: int) -> bool | None:
    """
    ¿El contenedor sigue existiendo en el clúster? ``None`` si no se pudo saber.

    La distinción importa: "no existe" habilita cerrar el registro, mientras
    que "no se pudo verificar" obliga a ser conservador y no marcar nada.
    """
    try:
        return any(
            int(r.get("vmid", -1)) == vmid for r in pve.listar_lxc_del_cluster()
        )
    except Exception as exc:
        logger.warning(f"No se pudo verificar si el VMID {vmid} sigue en el clúster: {exc}")
        return None


async def sincronizar_estados(
    db: AsyncSession,
    servicios: list[Servicio],
) -> list[Servicio]:
    """
    Reconcilia el estado guardado de cada servicio con el real en Proxmox.

    Proxmox es la fuente de verdad: el registro del portal se desfasa cuando el
    clúster se apaga y vuelve, cuando alguien toca el contenedor desde Proxmox,
    o cuando una acción falla a mitad de camino. Sin esta reconciliación la
    vista ofrecía "Detener" sobre un contenedor ya apagado y rechazaba
    "Iniciar" con un 409 porque el registro seguía diciendo RUNNING.

    Marca cada servicio con dos atributos de instancia (no persistidos) para
    que el frontend pueda decir la verdad en cada caso:

      - `estado_sincronizado`: el estado se confirmó contra Proxmox.
      - `existe_en_proxmox`: True/False, o None si no se pudo averiguar.

    Un contenedor que ya no figura en el clúster no cambia de estado — el
    registro conserva el último conocido y queda marcado como inexistente. Dar
    de baja el registro es una decisión del administrador, no un efecto
    colateral de listar.
    """
    reales = _estados_reales_del_cluster()
    cambios = 0

    for servicio in servicios:
        real = None
        if reales is not None and servicio.proxmox_vmid:
            real = reales.get(int(servicio.proxmox_vmid))

        servicio.estado_sincronizado = real is not None
        # Sin VMID nunca hubo contenedor, y sin respuesta del clúster no hay
        # nada que afirmar: en ambos casos "no se sabe", que no es lo mismo
        # que "no existe".
        desconocido = reales is None or not servicio.proxmox_vmid
        servicio.existe_en_proxmox = None if desconocido else real is not None

        if real is not None and servicio.estado != real:
            logger.info(
                f"Servicio {servicio.id} (VMID={servicio.proxmox_vmid}): estado "
                f"registrado {servicio.estado.value} → real {real.value}"
            )
            servicio.estado = real
            cambios += 1

    if cambios:
        await db.commit()

    return servicios


async def sincronizar_estado(db: AsyncSession, servicio: Servicio) -> Servicio:
    """Reconcilia un único servicio contra Proxmox. Ver `sincronizar_estados`."""
    await sincronizar_estados(db, [servicio])
    return servicio


def _generar_hostname(catedra_id: int, pedido_id: int) -> str:
    """Genera un hostname único para el contenedor."""
    return f"cat{catedra_id}-svc{pedido_id}"


def _construir_config_lxc(
    vmid: int,
    hostname: str,
    template: RecursoTemplate,
    node: str,
    storage: str = "local-lvm",
) -> dict:
    """
    Construye los parámetros de creación del LXC para la API de Proxmox.
    Los valores base vienen del template; config_extra puede sobreescribir.
    """
    config = {
        "vmid": vmid,
        "hostname": hostname,
        "cores": template.default_vcpus,
        "memory": template.default_ram_mb,
        "rootfs": f"{storage}:{template.default_disk_gb}",
        "net0": "name=eth0,bridge=vmbr0,ip=dhcp",
        "start": 1,          # arranca automáticamente al crear
        "unprivileged": 1,   # contenedor sin privilegios (más seguro)
    }

    # Si el template tiene un OS template configurado, usarlo
    if template.os_template:
        config["ostemplate"] = template.os_template

    # Mergear config_extra del template si existe (permite overrides avanzados)
    if template.config_extra:
        config.update(template.config_extra)

    return config


def _resolver_vmid(pve, pedido: Pedido, hostname: str) -> tuple[int, dict | None]:
    """
    Decide qué VMID usar para (re)desplegar un pedido.

    Devuelve `(vmid, contenedor_existente)`. Cuando `contenedor_existente` no es
    None se trata de un huérfano de un fallo parcial propio: el contenedor ya
    está creado en el clúster y debe adoptarse en lugar de crear otro.

    Matriz (ver contracts/api.md y research R2):
      sin reserva                        -> VMID nuevo
      reserva libre                      -> reutilizar
      reserva ocupada, hostname propio   -> adoptar
      reserva ocupada, hostname ajeno    -> VMID nuevo
    """
    if not pedido.vmid_reservado:
        return pve.get_next_vmid(), None

    reservado = int(pedido.vmid_reservado)
    ocupante = next(
        (
            r
            for r in pve.listar_lxc_del_cluster()
            if int(r.get("vmid", -1)) == reservado
        ),
        None,
    )

    if ocupante is None:
        # La reserva sigue libre: se reutiliza.
        return reservado, None

    if ocupante.get("name") == hostname:
        # Es nuestro: quedó creado por un fallo parcial anterior.
        logger.warning(
            f"VMID {reservado} ya existe con hostname propio '{hostname}'. "
            f"Se adopta el contenedor en lugar de crear uno nuevo."
        )
        return reservado, ocupante

    # Lo tomó un tercero: se descarta la reserva.
    logger.warning(
        f"VMID reservado {reservado} fue tomado por '{ocupante.get('name')}'. "
        f"Se solicita uno nuevo."
    )
    return pve.get_next_vmid(), None


async def _ejecutar_despliegue(
    db: AsyncSession,
    pedido: Pedido,
    admin: Usuario,
    node: str | None = None,
    storage: str = "local-lvm",
) -> Servicio:
    """
    Aprovisiona el recurso en Proxmox para un pedido que ya está en EN_DESPLIEGUE.

    Punto de entrada compartido por el despliegue inicial y el reintento: ambos
    caminos difieren solo en la validación del estado previo, de modo que no
    puedan divergir (research R5).

    En caso de falla transiciona el pedido a ERROR y levanta 502.
    """
    template = await db.get(RecursoTemplate, pedido.template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template del pedido no encontrado")

    # Solo LXC por ahora (QEMU se agrega en iteración futura)
    if template.tipo != TipoRecurso.LXC:
        raise HTTPException(
            status_code=400,
            detail="Solo se soporta despliegue de contenedores LXC en esta versión",
        )

    pve = get_proxmox_client()
    hostname = _generar_hostname(pedido.catedra_id, pedido.id)

    try:
        vmid, adoptado = _resolver_vmid(pve, pedido, hostname)

        # Persistir la reserva ANTES de tocar Proxmox: si la creación falla, el
        # VMID queda registrado y un reintento puede reutilizarlo (research R1).
        if pedido.vmid_reservado != str(vmid):
            pedido.vmid_reservado = str(vmid)
            await db.commit()

        if adoptado is not None:
            node = adoptado.get("node") or node
            logger.info(f"Adoptando contenedor existente VMID={vmid} en nodo {node}")
        else:
            # Elegir nodo automáticamente si no se especificó
            if not node:
                nodes = pve.get_nodes()
                online = [n for n in nodes if n.get("status") == "online"]
                if not online:
                    raise RuntimeError("No hay nodos Proxmox disponibles (online)")
                # Elegir el nodo con menos carga de CPU
                node = min(online, key=lambda n: n.get("cpu", 1))["node"]

            config = _construir_config_lxc(vmid, hostname, template, node, storage)

            logger.info(
                f"Desplegando LXC: VMID={vmid}, hostname={hostname}, node={node}, "
                f"template={template.nombre}"
            )

            # Crear el LXC (síncrono con proxmoxer; Proxmox devuelve un task ID)
            task_id = pve.create_lxc(node, **config)

            logger.info(f"LXC creado en Proxmox. Task: {task_id}, VMID: {vmid}")

    except Exception as exc:
        error_msg = str(exc)
        logger.error(f"Error al desplegar pedido {pedido.id}: {error_msg}")

        # Transicionar a ERROR con descripción
        await cambiar_estado(
            db=db,
            pedido_id=pedido.id,
            nuevo_estado_str=EstadoPedido.ERROR.value,
            usuario=admin,
            comentario=f"Error Proxmox: {error_msg[:200]}",
        )

        raise HTTPException(
            status_code=502,
            detail=f"Error al crear recurso en Proxmox: {error_msg}",
        )

    # --- Registrar Servicio en la DB ---
    servicio = Servicio(
        catedra_id=pedido.catedra_id,
        pedido_id=pedido.id,
        template_id=pedido.template_id,
        proxmox_vmid=str(vmid),
        proxmox_node=node,
        tipo=template.tipo.value,
        estado=EstadoServicio.RUNNING,
        hostname=hostname,
        vcpus_asignados=template.default_vcpus,
        ram_asignada_mb=template.default_ram_mb,
        disk_asignado_gb=template.default_disk_gb,
        deployed_at=datetime.utcnow(),
    )
    db.add(servicio)
    await db.flush()

    # --- Transicionar pedido a ACTIVO ---
    detalle = "adoptado" if adoptado is not None else "desplegado"
    await cambiar_estado(
        db=db,
        pedido_id=pedido.id,
        nuevo_estado_str=EstadoPedido.ACTIVO.value,
        usuario=admin,
        comentario=(
            f"Contenedor {detalle}: VMID={vmid}, nodo={node}, hostname={hostname}"
        ),
    )

    await db.commit()
    await db.refresh(servicio)

    logger.info(f"Pedido {pedido.id} desplegado exitosamente → Servicio ID={servicio.id}")
    return servicio


async def desplegar_pedido(
    db: AsyncSession,
    pedido_id: int,
    admin: Usuario,
    node: str | None = None,
    storage: str = "local-lvm",
) -> Servicio:
    """
    Orquesta el despliegue completo de un pedido APROBADO:
    1. Valida que el pedido esté en estado APROBADO
    2. Transiciona a EN_DESPLIEGUE
    3. Delega el aprovisionamiento en `_ejecutar_despliegue`

    En caso de falla, el pedido queda en ERROR con el mensaje.
    """
    pedido = await db.get(Pedido, pedido_id)
    if not pedido or pedido.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")

    if pedido.estado != EstadoPedido.APROBADO:
        raise HTTPException(
            status_code=409,
            detail=f"Solo se pueden desplegar pedidos APROBADOS. Estado actual: {pedido.estado.value}",
        )

    await cambiar_estado(
        db=db,
        pedido_id=pedido_id,
        nuevo_estado_str=EstadoPedido.EN_DESPLIEGUE.value,
        usuario=admin,
        comentario="Iniciando despliegue en Proxmox VE",
    )

    return await _ejecutar_despliegue(db, pedido, admin, node, storage)


async def reintentar_despliegue(
    db: AsyncSession,
    pedido_id: int,
    admin: Usuario,
    node: str | None = None,
    storage: str = "local-lvm",
) -> Servicio:
    """
    Reintenta el despliegue de un pedido que quedó en ERROR.

    Es el ejecutor real de la transición ERROR → EN_DESPLIEGUE, que la máquina de
    estados declaraba válida pero que ningún código concretaba: el pedido quedaba
    atascado sin posibilidad de recuperación (research R5).

    Es pseudo-idempotente: reutiliza el VMID reservado o adopta el contenedor si
    quedó creado por un fallo parcial, de modo que repetirlo no duplica recursos.
    """
    pedido = await db.get(Pedido, pedido_id)
    if not pedido or pedido.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")

    if pedido.estado != EstadoPedido.ERROR:
        raise HTTPException(
            status_code=409,
            detail=(
                "Solo se pueden reintentar pedidos en estado ERROR. "
                f"Estado actual: {pedido.estado.value}"
            ),
        )

    await cambiar_estado(
        db=db,
        pedido_id=pedido_id,
        nuevo_estado_str=EstadoPedido.EN_DESPLIEGUE.value,
        usuario=admin,
        comentario="Reintentando despliegue en Proxmox VE",
    )

    return await _ejecutar_despliegue(db, pedido, admin, node, storage)


async def detener_servicio(
    db: AsyncSession,
    servicio_id: int,
    usuario: Usuario,
) -> Servicio:
    """Detiene un servicio activo en Proxmox. La cátedra puede detener los propios."""
    servicio = await db.get(Servicio, servicio_id)
    if not servicio or servicio.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Servicio no encontrado")

    requiere_propio_o_admin(servicio, usuario)

    # Contra el estado real, no contra el que quedó guardado: si el contenedor
    # ya está apagado en Proxmox, el 409 dice la verdad.
    await sincronizar_estado(db, servicio)

    if servicio.estado != EstadoServicio.RUNNING:
        raise HTTPException(
            status_code=409,
            detail=f"El servicio no está en ejecución (estado: {servicio.estado.value})",
        )

    pve = get_proxmox_client()
    try:
        vmid = int(servicio.proxmox_vmid)
        pve.stop_lxc(servicio.proxmox_node, vmid)
        servicio.estado = EstadoServicio.STOPPED
        servicio.estado_sincronizado = True
        await db.commit()
        await db.refresh(servicio)
        logger.info(f"Servicio {servicio_id} detenido (VMID={vmid})")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Error al detener: {str(exc)}")

    return servicio


async def iniciar_servicio(
    db: AsyncSession,
    servicio_id: int,
    usuario: Usuario,
) -> Servicio:
    """
    Inicia un servicio que no está corriendo. La cátedra puede iniciar los propios.

    Acepta cualquier estado que no sea RUNNING (detenido, pausado o en error):
    encender es la salida natural de todos ellos, y ese es justo el caso en que
    el portal quedó desfasado y hay que poder recuperar el contenedor. El
    estado se reconcilia antes contra Proxmox para no rechazar un arranque
    válido por un registro viejo.
    """
    servicio = await db.get(Servicio, servicio_id)
    if not servicio or servicio.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Servicio no encontrado")

    requiere_propio_o_admin(servicio, usuario)

    await sincronizar_estado(db, servicio)

    if servicio.estado == EstadoServicio.RUNNING:
        raise HTTPException(
            status_code=409,
            detail="El servicio ya está en ejecución",
        )

    pve = get_proxmox_client()
    try:
        vmid = int(servicio.proxmox_vmid)
        pve.start_lxc(servicio.proxmox_node, vmid)
        servicio.estado = EstadoServicio.RUNNING
        servicio.estado_sincronizado = True
        await db.commit()
        await db.refresh(servicio)
        logger.info(f"Servicio {servicio_id} iniciado (VMID={vmid})")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Error al iniciar: {str(exc)}")

    return servicio


async def reiniciar_servicio(
    db: AsyncSession,
    servicio_id: int,
    usuario: Usuario,
) -> Servicio:
    """Reinicia un servicio en ejecución en Proxmox. La cátedra puede reiniciar los propios."""
    servicio = await db.get(Servicio, servicio_id)
    if not servicio or servicio.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Servicio no encontrado")

    requiere_propio_o_admin(servicio, usuario)

    await sincronizar_estado(db, servicio)

    if servicio.estado != EstadoServicio.RUNNING:
        raise HTTPException(
            status_code=409,
            detail=f"El servicio no está en ejecución (estado: {servicio.estado.value})",
        )

    pve = get_proxmox_client()
    try:
        vmid = int(servicio.proxmox_vmid)
        pve.reboot_lxc(servicio.proxmox_node, vmid)
        # El servicio sigue RUNNING antes y después: el reinicio lo gestiona
        # Proxmox internamente, no hay estado intermedio que persistir.
        logger.info(f"Servicio {servicio_id} reiniciado (VMID={vmid})")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Error al reiniciar: {str(exc)}")

    return servicio


async def emitir_ticket_consola(
    db: AsyncSession,
    servicio_id: int,
    usuario: Usuario,
) -> ConsolaTicketResponse:
    """
    Emite un ticket de consola propio del portal para un servicio en ejecución.

    Deliberadamente NO llama todavía a Proxmox (``abrir_termproxy``): ese ticket de
    Proxmox está atado a un puerto que su lado solo mantiene abierto un rato corto
    esperando una conexión, así que pedirlo acá y usarlo recién cuando el navegador
    complete el round-trip de abrir el WebSocket puede llegar tarde. En cambio, este
    ticket propio solo guarda node/vmid; la llamada a Proxmox se hace recién en la
    ruta WebSocket, inmediatamente antes de conectar (ver research.md R2-R4 de la
    spec 003).
    """
    servicio = await db.get(Servicio, servicio_id)
    if not servicio or servicio.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Servicio no encontrado")

    requiere_propio_o_admin(servicio, usuario)

    if servicio.estado != EstadoServicio.RUNNING:
        raise HTTPException(
            status_code=409,
            detail=f"El servicio debe estar en ejecución para abrir la consola (estado: {servicio.estado.value})",
        )

    ticket = secrets.token_urlsafe(32)
    _tickets_consola[ticket] = {
        "servicio_id": servicio_id,
        "usuario_id": usuario.id,
        "node": servicio.proxmox_node,
        "vmid": int(servicio.proxmox_vmid),
        "expira_at": datetime.utcnow() + timedelta(seconds=TICKET_CONSOLA_TTL_SEGUNDOS),
    }
    logger.info(f"Ticket de consola emitido para servicio {servicio_id} (usuario={usuario.id})")

    return ConsolaTicketResponse(ticket=ticket, expira_en_segundos=TICKET_CONSOLA_TTL_SEGUNDOS)


def consumir_ticket_consola(servicio_id: int, ticket: str) -> dict | None:
    """
    Valida y consume un ticket de consola: un solo uso, no vencido, del servicio pedido.

    Devuelve ``{"node": ..., "vmid": ...}`` si es válido, o ``None`` si no (ticket
    inexistente, vencido, ya usado, o de otro servicio) — la ruta WebSocket cierra
    la conexión inmediatamente en ese caso.
    """
    datos = _tickets_consola.pop(ticket, None)
    if datos is None:
        return None
    if datos["servicio_id"] != servicio_id:
        return None
    if datos["expira_at"] < datetime.utcnow():
        return None
    return datos


async def eliminar_servicio(
    db: AsyncSession,
    servicio_id: int,
    admin: Usuario,
) -> dict:
    """
    Da de baja un servicio: libera el contenedor en Proxmox y marca el registro.

    La baja es lógica: la fila permanece para poder reconstruir el consumo
    histórico de la cátedra aunque el contenedor ya no exista (FR-007).

    El orden importa: si no se pudo liberar el recurso real, el registro NO se
    marca como dado de baja (FR-010). Lo contrario dejaría un contenedor vivo
    consumiendo cuota del clúster sin figurar en ningún listado.
    """
    servicio = await db.get(Servicio, servicio_id)
    if not servicio:
        raise HTTPException(status_code=404, detail="Servicio no encontrado")

    if servicio.deleted_at is not None:
        return {
            "message": f"El servicio {servicio_id} ya estaba dado de baja",
            "vmid": servicio.proxmox_vmid,
            "deleted_at": servicio.deleted_at,
        }

    # Un servicio que nunca llegó a desplegarse no tiene recurso real que liberar
    if servicio.proxmox_vmid and servicio.proxmox_node:
        pve = get_proxmox_client()
        vmid = int(servicio.proxmox_vmid)
        node = servicio.proxmox_node
        try:
            # Detener primero si está corriendo
            status = pve.get_lxc_status(node, vmid)
            if status.get("status") == "running":
                pve.stop_lxc(node, vmid)
                # Pequeña pausa para que Proxmox procese el stop
                await asyncio.sleep(2)

            pve.delete_lxc(node, vmid)
            logger.info(f"Servicio {servicio_id} eliminado de Proxmox (VMID={vmid})")

        except Exception as exc:
            # Que falle no siempre significa que el recurso siga ocupado: si el
            # contenedor ya no existe (lo borraron desde Proxmox), el objetivo
            # de FR-010 está cumplido igual y el registro debe poder cerrarse;
            # de lo contrario quedaría trabado para siempre. Solo se aborta si
            # el contenedor sigue vivo, o si no se puede verificar.
            if _existe_en_el_cluster(pve, vmid) is not False:
                raise HTTPException(
                    status_code=502,
                    detail=f"Error al eliminar en Proxmox: {str(exc)}",
                )
            logger.warning(
                f"El contenedor VMID={vmid} ya no existe en Proxmox ({exc}). "
                f"Se da de baja el registro del servicio {servicio_id} igualmente."
            )

    # Recién ahora, con el recurso real liberado, se marca la baja
    servicio.deleted_at = datetime.utcnow()
    await db.commit()

    return {
        "message": f"Servicio {servicio_id} dado de baja correctamente",
        "vmid": servicio.proxmox_vmid,
        "deleted_at": servicio.deleted_at,
    }
