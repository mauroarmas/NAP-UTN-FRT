"""Períodos aprobados: UTC inclusivo/exclusivo, sin extender recesos."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import exists, select
from sqlalchemy.orm import aliased

from app.models.calendario import CalendarioLectivo, PeriodoCalendario
from app.models.vigencia import VigenciaAutorizada
from app.utils.clock import db_utc
from app.utils.errors import error


@dataclass(frozen=True)
class VigenciaResuelta:
    desde: date
    hasta: date
    zona_horaria: str
    inicio_at: datetime
    fin_exclusivo_at: datetime
    calendario_id: int | None = None
    calendario_revision: int | None = None

    def contiene(self, instant):
        if instant.tzinfo is None:
            raise ValueError('Instante sin zona horaria')
        return self.inicio_at <= instant < self.fin_exclusivo_at


def resolver_fechas(desde, hasta, zona):
    if type(desde) is not date or type(hasta) is not date or desde > hasta:
        raise ValueError('Rango de fechas inválido')
    try:
        zone = ZoneInfo(zona)
        start = datetime.combine(desde, time.min, zone).astimezone(timezone.utc)
        end = datetime.combine(hasta + timedelta(days=1), time.min, zone).astimezone(timezone.utc)
    except (ZoneInfoNotFoundError, OverflowError, TypeError, ValueError):
        raise ValueError('Fecha o zona institucional inválida') from None
    return VigenciaResuelta(desde, hasta, zona, start, end)


async def resolver_solicitud(db, vigencia, zona='America/Argentina/Tucuman'):
    tipo = vigencia.get('tipo')
    if tipo == 'personalizado':
        try:
            return resolver_fechas(date.fromisoformat(vigencia['desde']), date.fromisoformat(vigencia['hasta']), zona)
        except (KeyError, ValueError, TypeError):
            raise error(422, 'vigencia_invalida', 'Indicá fechas completas y ordenadas') from None
    if tipo not in {'primer_cuatrimestre', 'segundo_cuatrimestre', 'anual'} or type(vigencia.get('anio_lectivo')) is not int:
        raise error(422, 'vigencia_invalida', 'Elegí modalidad y año lectivo')
    calendar = await db.scalar(select(CalendarioLectivo).where(CalendarioLectivo.anio == vigencia['anio_lectivo']))
    if calendar is None:
        raise error(422, 'calendario_no_configurado', 'El año lectivo no tiene calendario configurado')
    period = await db.scalar(select(PeriodoCalendario).where(
        PeriodoCalendario.calendario_id == calendar.id, PeriodoCalendario.tipo == tipo))
    if period is None:
        raise error(422, 'periodo_no_configurado', 'Faltan las fechas de ese período')
    value = resolver_fechas(period.desde, period.hasta, calendar.zona_horaria)
    return VigenciaResuelta(value.desde, value.hasta, value.zona_horaria, value.inicio_at,
                           value.fin_exclusivo_at, calendar.id, calendar.revision)


async def periodos_vigentes(db, servicio_id):
    replacement = aliased(VigenciaAutorizada)
    return list((await db.scalars(select(VigenciaAutorizada).where(
        VigenciaAutorizada.servicio_id == servicio_id, VigenciaAutorizada.revocada_at.is_(None),
        ~exists(select(replacement.id).where(replacement.sustituye_id == VigenciaAutorizada.id,
                                           replacement.revocada_at.is_(None))),
    ).order_by(VigenciaAutorizada.inicio_at))).all())


async def exigir_cobertura(db, servicio_id, instant):
    if instant.tzinfo is None:
        raise ValueError('Instante sin zona horaria')
    periods = await periodos_vigentes(db, servicio_id)
    for period in periods:
        if db_utc(period.inicio_at) <= instant < db_utc(period.fin_exclusivo_at):
            return period
    raise error(409, 'sin_cobertura_actual', 'El servicio no tiene vigencia autorizada en esta fecha')


def resumir_cobertura(periods, instant):
    ranges = sorted((db_utc(p.inicio_at), db_utc(p.fin_exclusivo_at)) for p in periods)
    merged = []
    for start, end in ranges:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    current = next(((start, end) for start, end in merged if start <= instant < end), None)
    future = next((start for start, end in merged if instant < start), None)
    past = max((end for start, end in merged if end <= instant), default=None)
    return {'cubierto': current is not None, 'inicio_actual': current[0] if current else None,
        'fin_actual': current[1] if current else None, 'proximo_inicio': future, 'fin_anterior': past,
        'estado': 'sin_regularizar' if not ranges else 'con_cobertura' if current else 'receso' if past and future else 'esperando_inicio' if future else 'vencido'}


async def anexar_cobertura(db, services, *, usuario=None):
    if not services:
        return services
    replacement = aliased(VigenciaAutorizada)
    rows = list((await db.scalars(select(VigenciaAutorizada).where(
        VigenciaAutorizada.servicio_id.in_([s.id for s in services]), VigenciaAutorizada.revocada_at.is_(None),
        ~exists(select(replacement.id).where(replacement.sustituye_id == VigenciaAutorizada.id,
            replacement.revocada_at.is_(None)))).order_by(VigenciaAutorizada.inicio_at))).all())
    grouped = {}
    for row in rows:
        grouped.setdefault(row.servicio_id, []).append(row)
    from app.models.servicio import EstadoServicio
    from app.models.compromiso_capacidad import CompromisoCapacidad
    from app.models.identidad_infraestructura import IdentidadInfraestructura
    from app.utils.clock import clock
    ledgers = {row.servicio_id: row for row in (await db.scalars(select(CompromisoCapacidad).where(
        CompromisoCapacidad.servicio_id.in_([s.id for s in services]), CompromisoCapacidad.liberado_at.is_(None)))).all()}
    identities = {row.id: row for row in (await db.scalars(select(IdentidadInfraestructura).where(
        IdentidadInfraestructura.id.in_([s.identidad_infraestructura_id for s in services if s.identidad_infraestructura_id])))).all()}
    for service in services:
        periods = grouped.get(service.id, [])
        coverage = resumir_cobertura(periods, clock.now())
        service.periodos_autorizados = [{'id': str(p.id), 'modalidad': p.modalidad, 'anio_lectivo': p.anio_lectivo,
            'desde': p.desde_local.isoformat(), 'hasta': p.hasta_local.isoformat(), 'zona_horaria': p.zona_horaria,
            'inicio_at': db_utc(p.inicio_at).isoformat(), 'fin_exclusivo_at': db_utc(p.fin_exclusivo_at).isoformat(),
            'sustituye_id': str(p.sustituye_id) if p.sustituye_id else None} for p in periods]
        service.cobertura_actual, service.estado_cobertura = coverage['cubierto'], coverage['estado']
        service.proximo_inicio, service.fin_efectivo_at = coverage['proximo_inicio'], coverage['fin_actual']
        service.fuente_observacion = 'worker' if service.observado_at else 'sin_observacion'
        ledger, identity = ledgers.get(service.id), identities.get(service.identidad_infraestructura_id)
        regular = bool(service.tipo == 'lxc' and service.asignacion_snapshot and service.nombre_snapshot and service.modelo_servicio and identity and ledger and periods
            and ledger.identidad_infraestructura_id == identity.id and not identity.ausencia_confirmada_at)
        uncertain = bool((ledger and ledger.estado == 'incierto') or (identity and identity.estado == 'incierta'))
        service.regularizacion_pendiente = not regular or uncertain
        service.regularizacion_legacy = service.tipo == 'lxc' and service.definicion_version_id is None
        actions = []
        if regular and not uncertain and not getattr(service, 'operation_id', None):
            actions.append('renovar')
            if service.estado == EstadoServicio.RUNNING:
                actions.append('stop')
                if coverage['cubierto']:
                    actions.append('restart')
            elif coverage['cubierto'] and service.estado in {EstadoServicio.STOPPED, EstadoServicio.PAUSED}:
                actions.append('start')
            if usuario and usuario.rol.value == 'admin':
                actions.append('delete')
        service.acciones_habilitadas = actions
        service.motivo_bloqueo = 'Hay una operación abierta' if getattr(service, 'operation_id', None) else (
            'La asignación requiere reconciliación' if uncertain else 'Regularizá asignación y períodos' if not regular else 'No hay cobertura en esta fecha' if not coverage['cubierto'] else None)
    return services
