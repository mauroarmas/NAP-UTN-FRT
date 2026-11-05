"""Calendario por año, correcciones versionadas e historia inmutable."""
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select, delete, text

from app.config import get_settings
from app.models.calendario import CalendarioLectivo, PeriodoCalendario, CalendarioHistorial
from app.schemas.calendario import CalendarioEscritura
from app.services.acceso_service import requiere_admin_actual
from app.services.idempotencia_service import ejecutar, ResultadoDecision
from app.utils.clock import clock
from app.utils.errors import error

MODALIDADES = ['primer_cuatrimestre', 'segundo_cuatrimestre', 'anual']


async def presentar(db, calendar):
    periods = list((await db.scalars(select(PeriodoCalendario).where(
        PeriodoCalendario.calendario_id == calendar.id).order_by(PeriodoCalendario.desde, PeriodoCalendario.tipo))).all())
    return {'anio': calendar.anio, 'revision': calendar.revision, 'zona_horaria': calendar.zona_horaria,
        'periodos': [{'tipo': p.tipo, 'desde': p.desde.isoformat(), 'hasta': p.hasta.isoformat()} for p in periods],
        'faltantes': [kind for kind in MODALIDADES if kind not in {p.tipo for p in periods}]}


async def obtener(db, anio):
    calendar = await db.scalar(select(CalendarioLectivo).where(CalendarioLectivo.anio == anio))
    if calendar is None:
        raise error(404, 'calendario_no_configurado', 'El año elegido no tiene calendario configurado')
    return await presentar(db, calendar)


async def guardar(db, anio, payload, *, actor, clave):
    actor = await requiere_admin_actual(db, actor)
    body = payload if isinstance(payload, CalendarioEscritura) else CalendarioEscritura.model_validate(payload)
    normalized = body.model_dump(mode='json')
    async def decide(session):
        if session.bind.dialect.name == 'postgresql':
            await session.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': 6000 + anio})
        calendar = await session.scalar(select(CalendarioLectivo).where(CalendarioLectivo.anio == anio)
            .with_for_update().execution_options(populate_existing=True))
        if (calendar.revision if calendar else 0) != body.revision_esperada:
            raise error(409, 'calendario_desactualizado', 'El calendario cambió. Recargá antes de guardar.')
        zone = get_settings().institutional_timezone
        try:
            ZoneInfo(zone)
        except (ZoneInfoNotFoundError, ValueError):
            raise error(502, 'zona_institucional_invalida', 'Configurá una zona horaria institucional válida') from None
        from app.services.vigencia_service import resolver_fechas
        try:
            for period in body.periodos:
                resolver_fechas(period.desde, period.hasta, zone)
        except ValueError:
            raise error(422, 'periodo_invalido', 'Las fechas deben permitir resolver el intervalo completo') from None
        previous = await presentar(session, calendar) if calendar else None
        if calendar is None:
            calendar = CalendarioLectivo(anio=anio, revision=1, zona_horaria=zone,
                actualizado_por=actor.id, created_at=clock.now(), updated_at=clock.now())
            session.add(calendar)
            await session.flush()
        else:
            calendar.revision += 1
            calendar.zona_horaria, calendar.actualizado_por, calendar.updated_at = zone, actor.id, clock.now()
            await session.execute(delete(PeriodoCalendario).where(PeriodoCalendario.calendario_id == calendar.id))
        session.add_all([PeriodoCalendario(calendario_id=calendar.id, **p.model_dump()) for p in body.periodos])
        await session.flush()
        result = await presentar(session, calendar)
        session.add(CalendarioHistorial(calendario_id=calendar.id, revision=calendar.revision,
            actor_usuario_id=actor.id, anterior=previous, nuevo=result, creado_at=clock.now()))
        return ResultadoDecision(201 if previous is None else 200, result)
    return await ejecutar(db, actor_id=actor.id, clave=clave, metodo='PUT', ruta=f'/calendarios/{anio}',
        payload=normalized, decidir=decide, target_tipo='calendario', target_id=anio)
