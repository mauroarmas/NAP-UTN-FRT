"""Incidentes versionados por evidencia consecutiva; silencio no es caída."""
from datetime import timedelta

from sqlalchemy import select, text

from app.models.incidente import Incidente
from app.models.metrica import MetricaSnapshot
from app.models.operacion_infraestructura import OperacionInfraestructura
from app.models.servicio import EstadoServicio, Servicio
from app.services.notificacion_service import encolar_aviso_servicio
from app.utils.clock import clock, db_utc

RULE_VERSION = 'observacion-1min-v1'
LABELS = {'caida': 'Caída confirmada', 'cpu_sostenida': 'Consumo sostenido de CPU',
    'ram_sostenida': 'Consumo sostenido de RAM', 'operacion_incierta': 'Operación sin resultado confirmado',
    'vencimiento_no_aplicado': 'Vencimiento pendiente de aplicar'}


def _confirmed(row):
    return bool(row and row.calidad == 'confirmada' and row.intervalo_at is not None)


def _condition(row, kind):
    if not _confirmed(row): return None
    if kind == 'caida':
        if row.estado_observado == 'stopped': return True
        if row.estado_observado == 'running' and row.aplicacion_saludable is not None:
            return not row.aplicacion_saludable
        return None
    if row.estado_observado != 'running': return None
    if kind == 'cpu_sostenida':
        return row.cpu_usage_percent > 90 if row.cpu_usage_percent is not None else None
    if kind == 'ram_sostenida':
        if row.ram_usage_mb is None or row.ram_max_mb is None or row.ram_max_mb <= 0: return None
        return row.ram_usage_mb * 100 / row.ram_max_mb > 90
    return None


def _two(rows, kind, value):
    if len(rows) < 2 or not all(_condition(r, kind) is value for r in rows[:2]): return False
    latest, previous = rows[:2]
    elapsed = (db_utc(latest.timestamp) - db_utc(previous.timestamp)).total_seconds()
    return (60 <= elapsed <= 120
        and db_utc(latest.intervalo_at) - db_utc(previous.intervalo_at) == timedelta(minutes=1))


def _sustained(rows, kind):
    if len(rows) < 16: return False
    latest = rows[0]
    previous = None
    for row in rows:
        if _condition(row, kind) is not True: return False
        if previous is not None:
            elapsed = (db_utc(previous.timestamp) - db_utc(row.timestamp)).total_seconds()
            if (not 0 < elapsed <= 120 or previous.duracion_observada_s == 0
                or db_utc(previous.intervalo_at) - db_utc(row.intervalo_at) != timedelta(minutes=1)):
                return False
        if db_utc(latest.timestamp) - db_utc(row.timestamp) >= timedelta(minutes=15): return True
        previous = row
    return False


async def _notice(db, service, incident, action):
    title = LABELS[incident.tipo] + (' — recuperado' if action == 'recuperacion' else '')
    await encolar_aviso_servicio(db, service, evento=f'incidente:{incident.id}:{action}', tipo='incidente_' + action,
        asunto=title, texto=f'{title} en el servicio #{service.id}. Consultá el portal para revisar el estado y los detalles.',
        incluir_admin=True)


async def _apply(db, service, kind, *, opened, recovered, at, evidence):
    incident = await db.scalar(select(Incidente).where(Incidente.servicio_id == service.id,
        Incidente.tipo == kind, Incidente.estado == 'abierto').with_for_update())
    if opened:
        if incident is None:
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            from sqlalchemy.dialects.sqlite import insert as sqlite_insert
            insert = pg_insert if db.bind.dialect.name == 'postgresql' else sqlite_insert
            identity = await db.scalar(insert(Incidente).values(servicio_id=service.id, tipo=kind,
                estado='abierto', abierto_at=at, ultima_observacion_at=at,
                regla_version=RULE_VERSION, evidencia=evidence)
                .on_conflict_do_nothing(index_elements=['servicio_id','tipo'], index_where=text("estado = 'abierto'"))
                .returning(Incidente.id))
            if identity:
                incident = await db.get(Incidente, identity)
                await _notice(db, service, incident, 'apertura')
                return 1
        elif at > db_utc(incident.ultima_observacion_at):
            incident.ultima_observacion_at = at
    elif recovered and incident is not None and at > db_utc(incident.abierto_at):
        incident.estado, incident.resuelto_at, incident.ultima_observacion_at = 'resuelto', at, at
        await _notice(db, service, incident, 'recuperacion')
        return 1
    return 0


async def evaluar_alertas(db):
    from app.services.vigencia_service import periodos_vigentes, resumir_cobertura
    ids = list((await db.scalars(select(Servicio.id).where(Servicio.deleted_at.is_(None)))).all())
    changes = 0
    for identity in ids:
        service = await db.scalar(select(Servicio).where(Servicio.id == identity).with_for_update()
            .execution_options(populate_existing=True))
        now = clock.now()
        rows = list((await db.scalars(select(MetricaSnapshot).where(MetricaSnapshot.servicio_id == identity,
            MetricaSnapshot.intervalo_at.is_not(None), MetricaSnapshot.timestamp <= now)
            .order_by(MetricaSnapshot.intervalo_at.desc()).limit(17))).all())
        latest = rows[0] if rows else None
        if (service.estado == EstadoServicio.RUNNING and latest
            and db_utc(latest.timestamp) >= now - timedelta(minutes=2)):
            at = db_utc(latest.timestamp)
            for kind in ['caida','cpu_sostenida','ram_sostenida']:
                opened = _two(rows, kind, True) if kind == 'caida' else _sustained(rows, kind)
                recovered = _two(rows, kind, False)
                changes += await _apply(db, service, kind, opened=opened, recovered=recovered, at=at,
                    evidence={'muestras': [r.id for r in rows], 'regla_version': RULE_VERSION})
        # Estos dos incidentes usan decisiones durables, sin consultar PVE.
        operations = list((await db.scalars(select(OperacionInfraestructura).where(
            OperacionInfraestructura.servicio_id == identity))).all())
        uncertain = any(op.estado == 'incierta' for op in operations)
        known_outcome = bool(operations and not any(op.estado in {'pendiente','en_curso','incierta'} for op in operations))
        changes += await _apply(db, service, 'operacion_incierta', opened=uncertain,
            recovered=known_outcome, at=now, evidence={'operaciones': [str(op.id) for op in operations if op.estado == 'incierta']})
        periods = await periodos_vigentes(db, identity)
        coverage = resumir_cobertura(periods, now)
        overdue = (service.estado == EstadoServicio.RUNNING and coverage['estado'] in {'vencido','receso'})
        changes += await _apply(db, service, 'vencimiento_no_aplicado', opened=overdue,
            recovered=bool(periods and (coverage['cubierto'] or service.estado in {EstadoServicio.STOPPED, EstadoServicio.PAUSED})),
            at=now, evidence={'estado_cobertura': coverage['estado']})
        await db.commit()
    return {'afectados': changes}
