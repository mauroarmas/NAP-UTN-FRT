"""Servicio de orquestación: despliega y gestiona recursos reales en Proxmox VE."""

import asyncio
import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException

from app.models.pedido import Pedido, PedidoHistorial, EstadoPedido
from app.models.servicio import Servicio, EstadoServicio
from app.models.recurso_template import RecursoTemplate, TipoRecurso
from app.models.usuario import Usuario
from app.services.proxmox_client import get_proxmox_client
from app.services.pedido_service import cambiar_estado

logger = logging.getLogger(__name__)


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
            for r in pve.get_cluster_resources("lxc")
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
    admin: Usuario,
) -> Servicio:
    """Detiene un servicio activo en Proxmox."""
    servicio = await db.get(Servicio, servicio_id)
    if not servicio or servicio.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Servicio no encontrado")

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
        await db.commit()
        await db.refresh(servicio)
        logger.info(f"Servicio {servicio_id} detenido (VMID={vmid})")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Error al detener: {str(exc)}")

    return servicio


async def iniciar_servicio(
    db: AsyncSession,
    servicio_id: int,
    admin: Usuario,
) -> Servicio:
    """Inicia un servicio detenido en Proxmox."""
    servicio = await db.get(Servicio, servicio_id)
    if not servicio or servicio.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Servicio no encontrado")

    if servicio.estado != EstadoServicio.STOPPED:
        raise HTTPException(
            status_code=409,
            detail=f"El servicio no está detenido (estado: {servicio.estado.value})",
        )

    pve = get_proxmox_client()
    try:
        vmid = int(servicio.proxmox_vmid)
        pve.start_lxc(servicio.proxmox_node, vmid)
        servicio.estado = EstadoServicio.RUNNING
        await db.commit()
        await db.refresh(servicio)
        logger.info(f"Servicio {servicio_id} iniciado (VMID={vmid})")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Error al iniciar: {str(exc)}")

    return servicio


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
        try:
            vmid = int(servicio.proxmox_vmid)
            node = servicio.proxmox_node

            # Detener primero si está corriendo
            status = pve.get_lxc_status(node, vmid)
            if status.get("status") == "running":
                pve.stop_lxc(node, vmid)
                # Pequeña pausa para que Proxmox procese el stop
                await asyncio.sleep(2)

            pve.delete_lxc(node, vmid)
            logger.info(f"Servicio {servicio_id} eliminado de Proxmox (VMID={vmid})")

        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Error al eliminar en Proxmox: {str(exc)}",
            )

    # Recién ahora, con el recurso real liberado, se marca la baja
    servicio.deleted_at = datetime.utcnow()
    await db.commit()

    return {
        "message": f"Servicio {servicio_id} dado de baja correctamente",
        "vmid": servicio.proxmox_vmid,
        "deleted_at": servicio.deleted_at,
    }
