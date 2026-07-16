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
    3. Obtiene VMID del clúster
    4. Crea el LXC en Proxmox
    5. Registra el Servicio en la DB
    6. Transiciona a ACTIVO

    En caso de falla, transiciona a ERROR con el mensaje.
    """
    # --- 1. Cargar y validar pedido ---
    pedido = await db.get(Pedido, pedido_id)
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")

    if pedido.estado != EstadoPedido.APROBADO:
        raise HTTPException(
            status_code=409,
            detail=f"Solo se pueden desplegar pedidos APROBADOS. Estado actual: {pedido.estado.value}",
        )

    template = await db.get(RecursoTemplate, pedido.template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template del pedido no encontrado")

    # Solo LXC por ahora (QEMU se agrega en iteración futura)
    if template.tipo != TipoRecurso.LXC:
        raise HTTPException(
            status_code=400,
            detail="Solo se soporta despliegue de contenedores LXC en esta versión",
        )

    # --- 2. Transicionar a EN_DESPLIEGUE ---
    await cambiar_estado(
        db=db,
        pedido_id=pedido_id,
        nuevo_estado_str=EstadoPedido.EN_DESPLIEGUE.value,
        usuario=admin,
        comentario="Iniciando despliegue en Proxmox VE",
    )

    # --- 3. Interactuar con Proxmox ---
    pve = get_proxmox_client()

    try:
        # Elegir nodo automáticamente si no se especificó
        if not node:
            nodes = pve.get_nodes()
            online = [n for n in nodes if n.get("status") == "online"]
            if not online:
                raise RuntimeError("No hay nodos Proxmox disponibles (online)")
            # Elegir el nodo con menos carga de CPU
            node = min(online, key=lambda n: n.get("cpu", 1))["node"]

        # Obtener siguiente VMID disponible
        vmid = pve.get_next_vmid()

        hostname = _generar_hostname(pedido.catedra_id, pedido.id)
        config = _construir_config_lxc(vmid, hostname, template, node, storage)

        logger.info(
            f"Desplegando LXC: VMID={vmid}, hostname={hostname}, node={node}, "
            f"template={template.nombre}"
        )

        # Crear el LXC (esto es síncrono con proxmoxer; Proxmox devuelve un task ID)
        task_id = pve.create_lxc(node, **config)

        logger.info(f"LXC creado en Proxmox. Task: {task_id}, VMID: {vmid}")

    except Exception as exc:
        error_msg = str(exc)
        logger.error(f"Error al desplegar pedido {pedido_id}: {error_msg}")

        # Transicionar a ERROR con descripción
        await cambiar_estado(
            db=db,
            pedido_id=pedido_id,
            nuevo_estado_str=EstadoPedido.ERROR.value,
            usuario=admin,
            comentario=f"Error Proxmox: {error_msg[:200]}",
        )

        raise HTTPException(
            status_code=502,
            detail=f"Error al crear recurso en Proxmox: {error_msg}",
        )

    # --- 4. Registrar Servicio en la DB ---
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

    # --- 5. Transicionar pedido a ACTIVO ---
    await cambiar_estado(
        db=db,
        pedido_id=pedido_id,
        nuevo_estado_str=EstadoPedido.ACTIVO.value,
        usuario=admin,
        comentario=f"Contenedor desplegado: VMID={vmid}, nodo={node}, hostname={hostname}",
    )

    await db.commit()
    await db.refresh(servicio)

    logger.info(f"Pedido {pedido_id} desplegado exitosamente → Servicio ID={servicio.id}")
    return servicio


async def detener_servicio(
    db: AsyncSession,
    servicio_id: int,
    admin: Usuario,
) -> Servicio:
    """Detiene un servicio activo en Proxmox."""
    servicio = await db.get(Servicio, servicio_id)
    if not servicio:
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
    if not servicio:
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
    """Elimina un servicio y su contenedor de Proxmox."""
    servicio = await db.get(Servicio, servicio_id)
    if not servicio:
        raise HTTPException(status_code=404, detail="Servicio no encontrado")

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

    # Eliminar de la DB
    await db.delete(servicio)
    await db.commit()

    return {"message": f"Servicio {servicio_id} eliminado correctamente", "vmid": servicio.proxmox_vmid}
