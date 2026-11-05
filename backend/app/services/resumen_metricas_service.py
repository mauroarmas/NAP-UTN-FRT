"""Integrales diarias y purga condicionada; el detalle ausente sigue desconocido."""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select

from app.config import get_settings
from app.models.metrica import MetricaSnapshot
from app.models.metricas_resumen import MetricaResumenDiario
from app.models.servicio import Servicio
from app.models.servicio_historial import ServicioHistorial
from app.utils.clock import clock, db_utc


def limites_dia(day, zone):
    tz = ZoneInfo(zone)
    return (datetime.combine(day, time.min, tz).astimezone(timezone.utc),
        datetime.combine(day + timedelta(days=1), time.min, tz).astimezone(timezone.utc))


def _allocation(history, start, end):
    """Segmentar solo con asignaciones registradas; nunca consultar el template."""
    events = [(db_utc(row.created_at), row.decision_metadata) for row in history
        if row.decision_metadata and isinstance(row.decision_metadata.get('asignacion'), dict)]
    points = sorted({start, end, *(at for at, _ in events if start < at < end)})
    totals = [0, 0, 0]
    for a, b in zip(points, points[1:]):
        current = next((value['asignacion'] for at, value in reversed(events) if at <= a), None)
        if current is None: return None
        values = [current.get(key) for key in ['vcpus','ram_mb','disk_gb']]
        if any(type(v) is not int or v <= 0 for v in values): return None
        seconds = int((b - a).total_seconds())
        for i, value in enumerate(values): totals[i] += value * seconds * (1024**3 if i == 2 else 1)
    return totals


async def agregar_dia(db, *, servicio_id: int, fecha_local: date, zona_horaria: str):
    start, end = limites_dia(fecha_local, zona_horaria)
    key = (servicio_id, fecha_local, zona_horaria)
    existing = await db.get(MetricaResumenDiario, key, populate_existing=True)
    if existing and existing.detalle_purgado_at is not None: return existing
    service = await db.get(Servicio, servicio_id)
    if not service: raise ValueError('Servicio histórico inexistente')
    rows = list((await db.scalars(select(MetricaSnapshot).where(MetricaSnapshot.servicio_id == servicio_id,
        MetricaSnapshot.timestamp >= start, MetricaSnapshot.timestamp < end + timedelta(seconds=120),
        MetricaSnapshot.timestamp <= clock.now(), MetricaSnapshot.calidad == 'confirmada',
        MetricaSnapshot.intervalo_at.is_not(None)).order_by(MetricaSnapshot.timestamp))).all())
    history = list((await db.scalars(select(ServicioHistorial).where(ServicioHistorial.servicio_id == servicio_id,
        ServicioHistorial.created_at <= end.replace(tzinfo=None)).order_by(ServicioHistorial.created_at, ServicioHistorial.id))).all())
    values = dict(servicio_id=servicio_id, fecha_local=fecha_local, zona_horaria=zona_horaria,
        catedra_id=service.catedra_id, intervalos_esperados=int((end-start).total_seconds()//60),
        intervalos_validos=len({db_utc(row.intervalo_at) for row in rows if start <= db_utc(row.intervalo_at) < end}),
        segundos_observados=0, cpu_integral=0.0, cpu_max=None, ram_integral_mb_s=0.0, ram_max_mb=None,
        disk_max_bytes=None, trafico_in_bytes=0, trafico_out_bytes=0, segundos_running=0,
        vcpu_segundos=0, ram_asignada_mb_segundos=0, disk_asignado_byte_segundos=0,
        periodo_cerrado=clock.now() >= end + timedelta(minutes=2), agregado_at=clock.now())
    unknown_allocation = False
    for row in rows:
        at = db_utc(row.timestamp)
        inside = start <= at < end
        if inside:
            for target, source in [('cpu_max','cpu_usage_percent'),('ram_max_mb','ram_usage_mb'),('disk_max_bytes','disk_max_bytes')]:
                value = getattr(row, source)
                if value is not None: values[target] = value if values[target] is None else max(values[target], value)
            if row.net_in_delta is not None: values['trafico_in_bytes'] += row.net_in_delta
            if row.net_out_delta is not None: values['trafico_out_bytes'] += row.net_out_delta
        a, b = max(start, at-timedelta(seconds=row.duracion_observada_s)), min(end, at)
        seconds = max(0, int((b-a).total_seconds()))
        if not seconds: continue
        values['segundos_observados'] += seconds
        if row.cpu_usage_percent is not None: values['cpu_integral'] += row.cpu_usage_percent * seconds
        if row.ram_usage_mb is not None: values['ram_integral_mb_s'] += row.ram_usage_mb * seconds
        if row.estado_observado == 'running':
            values['segundos_running'] += seconds
            allocated = _allocation(history, a, b)
            if allocated is None: unknown_allocation = True
            else:
                for field, number in zip(['vcpu_segundos','ram_asignada_mb_segundos','disk_asignado_byte_segundos'], allocated):
                    values[field] += number
    if unknown_allocation:
        for field in ['vcpu_segundos','ram_asignada_mb_segundos','disk_asignado_byte_segundos']: values[field] = None
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    insert = pg_insert if db.bind.dialect.name == 'postgresql' else sqlite_insert
    await db.execute(insert(MetricaResumenDiario).values(**values).on_conflict_do_update(
        index_elements=['servicio_id','fecha_local','zona_horaria'], set_={k:v for k,v in values.items() if k not in {'servicio_id','fecha_local','zona_horaria'}},
        where=MetricaResumenDiario.detalle_purgado_at.is_(None)))
    await db.flush()
    return await db.get(MetricaResumenDiario, key, populate_existing=True)


async def purgar_detalle(db):
    cutoff = clock.now() - timedelta(days=90)
    summaries = list((await db.scalars(select(MetricaResumenDiario).where(
        MetricaResumenDiario.periodo_cerrado.is_(True), MetricaResumenDiario.detalle_purgado_at.is_(None)))).all())
    removed = 0
    for summary in summaries:
        start, end = limites_dia(summary.fecha_local, summary.zona_horaria)
        if end > cutoff: continue
        conditions = [MetricaSnapshot.servicio_id == summary.servicio_id, MetricaSnapshot.timestamp >= start,
            MetricaSnapshot.timestamp < end, MetricaSnapshot.intervalo_at.is_not(None)]
        edge = await db.scalar(select(MetricaSnapshot.id).where(*conditions)
            .order_by(MetricaSnapshot.timestamp.desc(), MetricaSnapshot.id.desc()).limit(1))
        if edge is not None:
            result = await db.execute(delete(MetricaSnapshot).where(*conditions, MetricaSnapshot.id != edge)
                .execution_options(synchronize_session='fetch'))
            removed += result.rowcount
        summary.detalle_purgado_at = clock.now()
    await db.flush()
    return removed


async def agregar_y_purgar(db):
    # Importar la fachada permite que el mismo ejecutor/manual comparta contrato.
    from app.services import metricas_service
    zone = get_settings().institutional_timezone
    today = clock.now().astimezone(ZoneInfo(zone)).date()
    candidates = (await db.execute(select(MetricaSnapshot.servicio_id, func.min(MetricaSnapshot.timestamp)).where(
        MetricaSnapshot.intervalo_at.is_not(None))
        .group_by(MetricaSnapshot.servicio_id))).all()
    closed = set((await db.execute(select(MetricaResumenDiario.servicio_id, MetricaResumenDiario.fecha_local).where(
        MetricaResumenDiario.zona_horaria == zone, MetricaResumenDiario.periodo_cerrado.is_(True)))).all())
    for identity, oldest in candidates:
        day = db_utc(oldest).astimezone(ZoneInfo(zone)).date()
        while day <= today:
            if (identity, day) not in closed:
                await metricas_service.agregar_dia(db, servicio_id=identity, fecha_local=day, zona_horaria=zone)
            day += timedelta(days=1)
    count = await purgar_detalle(db)
    await db.commit()
    return {'afectados': count}


async def consultar_consumo(db, *, catedra_id: int, desde: date, hasta: date, limit=500, offset=0, zona_horaria=None):
    if hasta <= desde: raise ValueError('Período inválido')
    return list((await db.scalars(select(MetricaResumenDiario).where(MetricaResumenDiario.catedra_id == catedra_id,
        MetricaResumenDiario.fecha_local >= desde, MetricaResumenDiario.fecha_local < hasta,
        MetricaResumenDiario.zona_horaria == (zona_horaria or get_settings().institutional_timezone))
        .order_by(MetricaResumenDiario.fecha_local, MetricaResumenDiario.servicio_id)
        .limit(max(1,min(limit,500))).offset(max(0,offset)))).all())
