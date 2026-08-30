"""Vencimiento de servicios: la vía garantizada de recuperación de capacidad.

A diferencia del pausado por inactividad, no depende de medir nada ni de que la
recolección de métricas esté sana. Una fecha de fin es determinista, predecible
para la cátedra desde el primer día, y pareja para todos.

Además cierra el modelo: el mismo punto de control que otorga los recursos —la
aprobación del administrador— es el que los recupera, porque renovar es pedir de
nuevo.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pedido import EstadoPedido, Pedido, TipoPedido
from app.models.servicio import EstadoServicio, Servicio
from app.services import historial_service, scheduler
from app.services.proxmox_client import get_proxmox_client

logger = logging.getLogger(__name__)

# Duración por defecto de un servicio nuevo. Conservadora a propósito: una fecha
# corta apagaría trabajo en plena cursada, y el costo de renovar de más es mucho
# menor que el de interrumpir una clase.
VIGENCIA_POR_DEFECTO = timedelta(days=180)

# Cuánto antes se le avisa a la cátedra.
AVISO_ANTICIPACION = timedelta(days=7)


def vencimiento_por_defecto(desde: datetime | None = None) -> datetime:
    return (desde or datetime.utcnow()) + VIGENCIA_POR_DEFECTO


async def tiene_renovacion_pendiente(db: AsyncSession, servicio_id: int) -> bool:
    """¿Hay una renovación esperando decisión del administrador?"""
    resultado = await db.execute(
        select(Pedido).where(
            Pedido.servicio_id == servicio_id,
            Pedido.tipo == TipoPedido.RENOVACION,
            Pedido.deleted_at.is_(None),
            Pedido.estado.in_(
                [EstadoPedido.SOLICITADO, EstadoPedido.APROBADO, EstadoPedido.EN_DESPLIEGUE]
            ),
        )
    )
    return resultado.scalars().first() is not None


async def aplicar_vencimientos(db: AsyncSession) -> dict:
    """Apaga los servicios vencidos y avisa de los próximos a vencer.

    Tres decisiones que valen la pena señalar:

    - Un servicio con renovación pendiente **no** se apaga: castigarlo por la
      demora del administrador sería cobrarle a la cátedra un problema ajeno.
    - Los datos no se destruyen. Liberar almacenamiento sigue siendo una
      decisión humana.
    - Un servicio ya pausado no vuelve a descontar capacidad: la pausa ya la
      liberó. Solo se le marca el vencimiento.
    """
    ahora = datetime.utcnow()
    pve = get_proxmox_client()

    vencidos, avisados, postergados = [], [], []

    candidatos = (
        (
            await db.execute(
                select(Servicio).where(
                    Servicio.deleted_at.is_(None),
                    Servicio.vence_at.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )

    for servicio in candidatos:
        # Aviso previo: la cátedra tiene que poder reaccionar antes.
        if (
            servicio.vence_at - AVISO_ANTICIPACION <= ahora < servicio.vence_at
            and servicio.aviso_vencimiento_at is None
        ):
            servicio.aviso_vencimiento_at = ahora
            avisados.append(servicio.id)
            continue

        if servicio.vence_at > ahora:
            continue

        if await tiene_renovacion_pendiente(db, servicio.id):
            postergados.append(servicio.id)
            continue

        if servicio.estado == EstadoServicio.PAUSED:
            # Ya liberó su cómputo al pausarse; no hay nada que descontar otra vez.
            db.add(
                historial_service.registrar_servicio(
                    servicio.id,
                    servicio.estado.value,
                    servicio.estado.value,
                    comentario=f"Vencido el {servicio.vence_at:%Y-%m-%d} (ya estaba pausado)",
                    usuario=None,
                )
            )
            vencidos.append(servicio.id)
            continue

        anterior = servicio.estado.value
        try:
            if servicio.proxmox_vmid and servicio.proxmox_node:
                pve.stop_lxc(servicio.proxmox_node, int(servicio.proxmox_vmid))
        except Exception as exc:
            logger.warning(
                "No se pudo detener el servicio %s al vencer: %s", servicio.id, exc
            )
            continue

        servicio.estado = EstadoServicio.PAUSED
        db.add(
            historial_service.registrar_servicio(
                servicio.id,
                anterior,
                EstadoServicio.PAUSED.value,
                comentario=(
                    f"Vencido el {servicio.vence_at:%Y-%m-%d}: se liberó cómputo y "
                    "memoria. Los datos se conservan."
                ),
                usuario=None,
            )
        )
        vencidos.append(servicio.id)

    await db.commit()
    return {
        "afectados": len(vencidos),
        "detalle": vencidos,
        "avisados": avisados,
        "postergados_por_renovacion": postergados,
    }


scheduler.registrar("aplicar_vencimientos", aplicar_vencimientos, cada_minutos=60)
