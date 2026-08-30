"""Pausado de servicios sin uso: recuperación oportunista de capacidad.

Complementa al vencimiento, que es la vía garantizada. Este mecanismo es un
heurístico y se diseña asumiéndolo: puede equivocarse en las dos direcciones,
así que sus defensas importan más que su agresividad.

Sobre la palabra "pausar": en Proxmox, pausar o suspender un contenedor congela
los procesos pero **mantiene la memoria reservada**, y la hibernación real solo
es confiable en máquinas virtuales. Para un contenedor, detenerlo es lo que
libera CPU y RAM de verdad; el disco es persistente, así que los datos quedan
intactos y el arranque posterior demora segundos. Esa es la mecánica que se usa.
"Pausado" se conserva como el término de cara a la cátedra porque describe
correctamente lo que percibe.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.metrica import MetricaSnapshot
from app.models.pedido import EstadoPedido, Pedido
from app.models.servicio import EstadoServicio, Servicio
from app.services import historial_service, scheduler
from app.services.proxmox_client import get_proxmox_client

logger = logging.getLogger(__name__)

# Ventana de observación y período de gracia entre el aviso y la pausa.
VENTANA_INACTIVIDAD = timedelta(days=7)
GRACIA = timedelta(hours=48)

# Cadencia de la recolección de métricas, usada para estimar cuántas muestras
# debería haber en la ventana.
CADENCIA_METRICAS_MINUTOS = 15

# Fracción mínima de muestras esperadas para considerar que hubo observación.
# Sin esto, una recolección caída se vería igual que un servicio sin uso, y el
# sistema apagaría trabajo en curso: el peor error posible de esta feature, más
# caro que no pausar nunca nada.
COBERTURA_MINIMA = 0.8

UMBRAL_CPU = 5.0        # porcentaje
UMBRAL_RED_BYTES = 1_000_000  # tráfico acumulado en la ventana


def _muestras_esperadas(ventana: timedelta) -> int:
    return int(ventana.total_seconds() // (CADENCIA_METRICAS_MINUTOS * 60))


async def evaluar_actividad(db: AsyncSession, servicio: Servicio) -> dict:
    """¿Este servicio estuvo sin uso durante la ventana?

    Devuelve también por qué, para que la decisión sea auditable y para poder
    distinguir "no lo usó nadie" de "no lo miramos".
    """
    desde = datetime.utcnow() - VENTANA_INACTIVIDAD

    fila = (
        await db.execute(
            select(
                func.count(MetricaSnapshot.id),
                func.coalesce(func.max(MetricaSnapshot.cpu_usage_percent), 0.0),
                func.coalesce(func.sum(MetricaSnapshot.net_in_bytes), 0.0),
                func.coalesce(func.sum(MetricaSnapshot.net_out_bytes), 0.0),
            ).where(
                MetricaSnapshot.servicio_id == servicio.id,
                MetricaSnapshot.timestamp >= desde,
            )
        )
    ).one()
    muestras, cpu_max, net_in, net_out = fila

    esperadas = _muestras_esperadas(VENTANA_INACTIVIDAD)
    cobertura = (muestras / esperadas) if esperadas else 0.0

    if cobertura < COBERTURA_MINIMA:
        return {
            "inactivo": False,
            "motivo": "sin_cobertura",
            "detalle": (
                f"solo {muestras} de ~{esperadas} muestras esperadas "
                f"({cobertura:.0%}); la falta de medición no es inactividad"
            ),
        }

    trafico = float(net_in) + float(net_out)
    inactivo = float(cpu_max) < UMBRAL_CPU and trafico < UMBRAL_RED_BYTES
    return {
        "inactivo": inactivo,
        "motivo": "sin_uso" if inactivo else "con_uso",
        "detalle": f"CPU máx {float(cpu_max):.1f}%, tráfico {trafico:.0f} bytes",
    }


async def _tiene_operacion_en_curso(db: AsyncSession, servicio: Servicio) -> bool:
    """¿Hay un despliegue u otra operación del portal en vuelo sobre este servicio?

    Pausar en medio de un despliegue dejaría el recurso en un estado ambiguo.
    """
    if servicio.estado == EstadoServicio.ERROR:
        return True
    if servicio.pedido_id is None:
        return False
    pedido = await db.get(Pedido, servicio.pedido_id)
    return pedido is not None and pedido.estado == EstadoPedido.EN_DESPLIEGUE


async def evaluar_inactividad(db: AsyncSession) -> dict:
    """Avisa, programa y ejecuta la pausa de lo que nadie usa."""
    ahora = datetime.utcnow()
    pve = get_proxmox_client()
    avisados, pausados, cancelados, omitidos = [], [], [], []

    servicios = (
        (
            await db.execute(
                select(Servicio).where(
                    Servicio.deleted_at.is_(None),
                    Servicio.estado == EstadoServicio.RUNNING,
                )
            )
        )
        .scalars()
        .all()
    )

    for servicio in servicios:
        if servicio.exento_pausado:
            omitidos.append({"id": servicio.id, "motivo": "siempre_encendido"})
            continue

        if await _tiene_operacion_en_curso(db, servicio):
            omitidos.append({"id": servicio.id, "motivo": "operacion_en_curso"})
            continue

        veredicto = await evaluar_actividad(db, servicio)

        if not veredicto["inactivo"]:
            # Registró actividad (o no hay datos): se cancela cualquier pausa
            # programada. El aviso no se cumple si el servicio volvió a usarse.
            if servicio.pausa_programada_at is not None:
                servicio.pausa_programada_at = None
                servicio.aviso_pausa_at = None
                cancelados.append(servicio.id)
            else:
                omitidos.append({"id": servicio.id, "motivo": veredicto["motivo"]})
            continue

        if servicio.pausa_programada_at is None:
            # Primero se avisa; recién después de la gracia se apaga.
            servicio.aviso_pausa_at = ahora
            servicio.pausa_programada_at = ahora + GRACIA
            avisados.append(servicio.id)
            continue

        if servicio.pausa_programada_at > ahora:
            continue  # todavía en período de gracia

        try:
            if servicio.proxmox_vmid and servicio.proxmox_node:
                pve.stop_lxc(servicio.proxmox_node, int(servicio.proxmox_vmid))
        except Exception as exc:
            logger.warning("No se pudo pausar el servicio %s: %s", servicio.id, exc)
            continue

        anterior = servicio.estado.value
        servicio.estado = EstadoServicio.PAUSED
        servicio.pausado_auto_at = ahora
        servicio.pausa_programada_at = None
        db.add(
            historial_service.registrar_servicio(
                servicio.id,
                anterior,
                EstadoServicio.PAUSED.value,
                comentario=(
                    f"Sin uso desde {(ahora - VENTANA_INACTIVIDAD):%Y-%m-%d}: se "
                    "liberaron cómputo y memoria. El almacenamiento sigue ocupado."
                ),
                usuario=None,
            )
        )
        pausados.append(servicio.id)

    await db.commit()
    return {
        "afectados": len(pausados),
        "detalle": pausados,
        "avisados": avisados,
        "cancelados": cancelados,
        "omitidos": omitidos,
    }


async def reactivar(db: AsyncSession, servicio: Servicio, usuario) -> Servicio:
    """Vuelve a encender un servicio pausado.

    Si el clúster no tiene capacidad, el servicio queda **pausado** con el
    motivo registrado: nunca en un estado ambiguo ni en error.
    """
    from fastapi import HTTPException

    from app.services import capacidad_service

    if servicio.estado != EstadoServicio.PAUSED:
        raise HTTPException(
            status_code=409,
            detail=f"El servicio no está pausado (está en '{servicio.estado.value}')",
        )

    estado = await capacidad_service.panorama(db)
    necesita = {
        "vcpus": servicio.vcpus_asignados,
        "ram_mb": servicio.ram_asignada_mb,
        # El disco ya está ocupado: reactivar no pide almacenamiento nuevo.
        "storage_gb": 0,
    }
    if capacidad_service.excede(estado["libre"], necesita):
        raise HTTPException(
            status_code=409,
            detail={
                "codigo": "sin_capacidad",
                "mensaje": (
                    "Ahora mismo el clúster no tiene capacidad libre para volver a "
                    "encender este servicio. Sigue pausado y sus datos están intactos; "
                    "pedile a un administrador que libere capacidad."
                ),
            },
        )

    pve = get_proxmox_client()
    try:
        pve.start_lxc(servicio.proxmox_node, int(servicio.proxmox_vmid))
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"No se pudo encender el servicio en la infraestructura: {exc}",
        )

    servicio.estado = EstadoServicio.RUNNING
    servicio.pausado_auto_at = None
    servicio.pausa_programada_at = None
    servicio.aviso_pausa_at = None
    db.add(
        historial_service.registrar_servicio(
            servicio.id,
            EstadoServicio.PAUSED.value,
            EstadoServicio.RUNNING.value,
            comentario="Reactivado por la cátedra",
            usuario=usuario,
        )
    )
    await db.commit()
    await db.refresh(servicio)
    return servicio


async def recolectar_metricas(db: AsyncSession) -> dict:
    """Envoltorio del trabajo periódico sobre la captura ya existente."""
    from app.services.metricas_service import capturar_todos_los_servicios

    resultado = await capturar_todos_los_servicios(db)
    return {"afectados": resultado.get("capturados", 0), "detalle": resultado}


scheduler.registrar("evaluar_inactividad", evaluar_inactividad, cada_minutos=60)
scheduler.registrar(
    "recolectar_metricas", recolectar_metricas, cada_minutos=CADENCIA_METRICAS_MINUTOS
)
