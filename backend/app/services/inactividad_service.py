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
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.metrica import MetricaSnapshot
from app.models.pedido import EstadoPedido, Pedido
from app.models.servicio import EstadoServicio, Servicio
from app.services import scheduler
from app.utils.clock import clock, db_utc

logger = logging.getLogger(__name__)

# Ventana de observación y período de gracia entre el aviso y la pausa.
VENTANA_INACTIVIDAD = timedelta(days=7)
GRACIA = timedelta(hours=48)

# Cadencia de la recolección de métricas, usada para estimar cuántas muestras
# debería haber en la ventana.
CADENCIA_METRICAS_MINUTOS = 1

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
    now = clock.now()
    end = now.replace(second=0, microsecond=0)
    since = end - VENTANA_INACTIVIDAD
    rows = list((await db.scalars(select(MetricaSnapshot).where(
        MetricaSnapshot.servicio_id == servicio.id, MetricaSnapshot.intervalo_at >= since,
        MetricaSnapshot.intervalo_at < end, MetricaSnapshot.calidad == 'confirmada',
        MetricaSnapshot.estado_observado == 'running', MetricaSnapshot.cpu_usage_percent.is_not(None)
    ))).all())
    expected = _muestras_esperadas(VENTANA_INACTIVIDAD)
    # Un delta nulo (hueco/reset) no significa cero tráfico. El entero Python
    # evita overflow al sumar contadores BIGINT; nunca se suman acumulados.
    valid = [r for r in rows if r.net_in_delta is not None and r.net_out_delta is not None
        and r.duracion_observada_s > 0
        and db_utc(r.timestamp) - timedelta(seconds=r.duracion_observada_s) >= since]
    count = len({db_utc(r.intervalo_at) for r in valid})
    coverage = count / expected
    traffic = sum(r.net_in_delta + r.net_out_delta for r in valid)
    cpu_max = max((r.cpu_usage_percent for r in rows), default=None)
    fresh = bool(valid and max(db_utc(r.timestamp) for r in valid) >= now - timedelta(minutes=2))
    reason = ('sin_cobertura' if coverage < COBERTURA_MINIMA else
        'sin_observacion_reciente' if not fresh else
        'sin_uso' if cpu_max is not None and cpu_max < UMBRAL_CPU and traffic < UMBRAL_RED_BYTES else 'con_uso')
    return {'inactivo': reason == 'sin_uso', 'motivo': reason, 'muestras': count, 'esperadas': expected,
        'cobertura': coverage, 'trafico_bytes': traffic, 'cpu_max': cpu_max,
        'detalle': f'{count}/{expected} intervalos confirmados; tráfico observado {traffic} bytes'}


async def _tiene_operacion_en_curso(db: AsyncSession, servicio: Servicio) -> bool:
    """¿Hay un despliegue u otra operación del portal en vuelo sobre este servicio?

    Pausar en medio de un despliegue dejaría el recurso en un estado ambiguo.
    """
    from app.models.operacion_infraestructura import OperacionInfraestructura
    if await db.scalar(select(OperacionInfraestructura.id).where(
        OperacionInfraestructura.servicio_id == servicio.id,
        OperacionInfraestructura.estado.in_(['pendiente', 'en_curso', 'incierta'])).limit(1)):
        return True
    if servicio.estado == EstadoServicio.ERROR:
        return True
    if servicio.pedido_id is None:
        return False
    pedido = await db.get(Pedido, servicio.pedido_id)
    return pedido is not None and pedido.estado == EstadoPedido.EN_DESPLIEGUE


async def evaluar_inactividad(db: AsyncSession) -> dict:
    """Avisa, programa y ejecuta la pausa de lo que nadie usa."""
    ahora = clock.now().replace(tzinfo=None)
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
                previous_notice = servicio.aviso_pausa_at or servicio.pausa_programada_at
                servicio.pausa_programada_at = None
                servicio.aviso_pausa_at = None
                await _aviso(db, servicio, 'cancelada', previous_notice)
                cancelados.append(servicio.id)
            else:
                omitidos.append({"id": servicio.id, "motivo": veredicto["motivo"]})
            continue

        if servicio.pausa_programada_at is None:
            # Primero se avisa; recién después de la gracia se apaga.
            servicio.aviso_pausa_at = ahora
            servicio.pausa_programada_at = ahora + GRACIA
            await _aviso(db, servicio, 'programada', ahora)
            avisados.append(servicio.id)
            continue

        if servicio.pausa_programada_at > ahora:
            continue  # todavía en período de gracia

        from app.services.operacion_service import admitir_orden
        from fastapi import HTTPException
        try:
            async with db.begin_nested():
                await admitir_orden(db, servicio.id, tipo='pausar', sistema='inactividad',
                    clave=f'inactividad:{servicio.id}:{servicio.pausa_programada_at.isoformat()}',
                    motivo='Finalizó el aviso por inactividad; detención pendiente de confirmación')
            pausados.append(servicio.id)
        except HTTPException:
            omitidos.append({'id': servicio.id, 'motivo': 'admision_no_confirmada'})

    await db.commit()
    return {
        "afectados": len(pausados),
        "detalle": pausados,
        "estado": "operaciones_admitidas",
        "avisados": avisados,
        "cancelados": cancelados,
        "omitidos": omitidos,
    }


async def _aviso(db, service, action, at):
    from app.services.notificacion_service import encolar_aviso_servicio
    title = 'Pausa por inactividad programada' if action == 'programada' else 'Pausa por inactividad cancelada'
    text = (f'El servicio #{service.id} tiene una pausa prevista tras 48 horas de gracia. '
        'Si vuelve a registrar actividad o falta observación suficiente, se cancelará. Consultá el portal.'
        if action == 'programada' else
        f'Se canceló la pausa prevista del servicio #{service.id}: no se confirma inactividad. Consultá el portal.')
    await encolar_aviso_servicio(db, service, evento=f'inactividad:{service.id}:{db_utc(at).isoformat()}:{action}',
        tipo='inactividad_' + action, asunto=title, texto=text)


async def reactivar(db, servicio, usuario, *, clave, motivo=None):
    from app.services.admision_service import iniciar
    return await iniciar(db, servicio.id, actor=usuario, clave=clave, motivo=motivo)


async def recolectar_metricas(db: AsyncSession) -> dict:
    """Envoltorio del trabajo periódico sobre la captura ya existente."""
    from app.services.metricas_service import capturar_todos_los_servicios

    resultado = await capturar_todos_los_servicios(db)
    return {"afectados": resultado.get("capturados", 0), "detalle": resultado}


scheduler.registrar("evaluar_inactividad", evaluar_inactividad, cada_minutos=60)
scheduler.registrar(
    "recolectar_metricas", recolectar_metricas, cada_minutos=CADENCIA_METRICAS_MINUTOS
)
