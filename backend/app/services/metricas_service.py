"""Observación por intervalos: consultas DB separadas del I/O de captura."""
import asyncio
from datetime import datetime, timedelta
import logging
import math
from uuid import uuid4, uuid5

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.identidad_infraestructura import IdentidadInfraestructura
from app.models.metrica import MetricaSnapshot
from app.models.servicio import Servicio
from app.services import identidad_infra_service as identities
from app.utils.clock import clock, db_utc

logger = logging.getLogger(__name__)
MAX_COUNTER = 2**63 - 1


def _counter(value):
    if type(value) is not int or not 0 <= value <= MAX_COUNTER:
        raise ValueError()
    return value


def _gauge(value, *, maximum=None):
    if type(value) not in {int, float} or not math.isfinite(value) or value < 0 or (maximum is not None and value > maximum):
        raise ValueError()
    return float(value)


async def observar_salud(request):
    """Solo una respuesta ligada a identidad confirma salud, nunca un timeout."""
    from app.schemas.guest_runner import parse_response, canonical
    from app.services.guest_runner_client import GuestRunnerClient
    try:
        response = parse_response(canonical(await GuestRunnerClient().execute(request)).encode(), request)
        at = db_utc(datetime.fromisoformat(response['observed_at'].replace('Z', '+00:00')))
        result = response.get('result', {})
        if (response['identity_verified'] and response['status'] in {'succeeded', 'pending'}
            and result.get('bootstrap_completed') is True and type(result.get('ready')) is bool
            and clock.now() - timedelta(minutes=1) <= at <= clock.now() + timedelta(seconds=5)):
            return result['ready']
    except Exception:
        # No registrar nonce, request, stderr ni representaciones de excepciones.
        pass
    return None


def _health_request(identity, service):
    from app.schemas.guest_runner import PROTOCOL
    from app.utils.secretos import configured_keyring
    assignment, metadata = service.asignacion_snapshot or {}, service.acceso_metadata or {}
    if not (identity.definition_sha256 and identity.bundle_sha256 and metadata.get('preparacion_id')):
        return None
    if (assignment.get('definition_sha256') != identity.definition_sha256
        or assignment.get('bundle_sha256') != identity.bundle_sha256):
        return None
    parameters, network = metadata.get('bootstrap_parameters'), metadata.get('bootstrap_network_profile_id')
    if not isinstance(parameters, dict) or not network:
        return None
    # inspect siempre vuelve a sondear; un UUID estable evita añadir una entrada
    # de deduplicación por minuto al estado persistente del runner.
    return {'protocol': PROTOCOL, 'operation_id': str(uuid5(identity.resource_uuid, 'nap-health-inspection-v1')), 'action': 'inspect',
        'cluster_uuid': identity.cluster_id, 'resource_uuid': str(identity.resource_uuid), 'node': identity.nodo,
        'vmid': identity.vmid, 'pool': identity.pool_catedra,
        'nonce': configured_keyring().decrypt(identity.nonce_cifrado, context=f'infra:{identity.resource_uuid}:nonce'),
        'definition_key': assignment['definition_key'], 'definition_version': assignment['definition_version'],
        'definition_sha256': identity.definition_sha256, 'bundle_sha256': identity.bundle_sha256,
        'network_profile_id': network, 'parameters': parameters}


async def capturar_snapshot_servicio(db: AsyncSession, servicio: Servicio) -> MetricaSnapshot | None:
    if not servicio.proxmox_vmid or not servicio.proxmox_node or servicio.tipo != 'lxc':
        return None
    service_id, identity_id = servicio.id, servicio.identidad_infraestructura_id
    now = clock.now()
    minute = now.replace(second=0, microsecond=0)
    # Reclamación durable antes del I/O. Un proceso interrumpido deja un minuto
    # desconocido; los visitantes no duplican el sondeo ni rellenan ese hueco.
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    insert = pg_insert if db.bind.dialect.name == 'postgresql' else sqlite_insert
    claimed = await db.scalar(insert(MetricaSnapshot).values(servicio_id=service_id,
        timestamp=now, intervalo_at=minute, calidad='no_confirmada', duracion_observada_s=0)
        .on_conflict_do_nothing(index_elements=['servicio_id', 'intervalo_at']).returning(MetricaSnapshot.id))
    await db.commit()
    if claimed is None:
        return await db.scalar(select(MetricaSnapshot).where(MetricaSnapshot.servicio_id == service_id,
            MetricaSnapshot.intervalo_at == minute).execution_options(populate_existing=True))
    sample = await db.get(MetricaSnapshot, claimed)
    try:
        identity = await db.get(IdentidadInfraestructura, identity_id) if identity_id else None
        if not identity or identity.ausencia_confirmada_at or identity.servicio_id != service_id:
            raise ValueError()
        health_request = _health_request(identity, servicio)
        # observar() toma copias primitivas antes de pasar su función al pool.
        observation = await identities.observar(identity)
        if observation.estado != 'propia' or not isinstance(observation.metricas, dict):
            raise ValueError()
        observed = clock.now()
        if observed.replace(second=0, microsecond=0) != minute:
            raise ValueError()
        payload = observation.metricas
        state = payload.get('status')
        if state not in {'running', 'stopped'}:
            raise ValueError()
        sample.timestamp, sample.estado_observado = observed, state
        if state == 'running':
            cpu = _gauge(payload.get('cpu'), maximum=1) * 100
            ram = _counter(payload.get('mem')) / 1024**2
            disk = _counter(payload.get('disk')) / 1024**3
            net_in, net_out = _counter(payload.get('netin')), _counter(payload.get('netout'))
            uptime = _counter(payload.get('uptime'))
            sample.cpu_usage_percent, sample.ram_usage_mb, sample.disk_usage_gb = cpu, ram, disk
            sample.net_in_bytes, sample.net_out_bytes, sample.uptime_s = net_in, net_out, uptime
            for field, source, scale in [('ram_max_mb','maxmem',1024**2), ('disk_max_bytes','maxdisk',1), ('vcpus_observadas','cpus',1)]:
                value = payload.get(source)
                if value is not None:
                    try:
                        value = _counter(value)
                        if value <= 0: raise ValueError()
                        setattr(sample, field, value / scale if scale != 1 else value)
                    except ValueError:
                        pass  # Límite no confirmado, sin reemplazarlo por el actual.
            previous = await db.scalar(select(MetricaSnapshot).where(MetricaSnapshot.servicio_id == service_id,
                MetricaSnapshot.intervalo_at < minute).order_by(desc(MetricaSnapshot.intervalo_at)).limit(1))
            sample.epoca_contador = str(uuid4())
            if (previous and previous.calidad == 'confirmada' and previous.estado_observado == 'running'
                and previous.uptime_s is not None and previous.net_in_bytes is not None and previous.net_out_bytes is not None):
                elapsed = (observed - db_utc(previous.timestamp)).total_seconds()
                continuous = elapsed > 0 and abs((uptime - previous.uptime_s) - elapsed) <= 2
                if continuous and net_in >= previous.net_in_bytes and net_out >= previous.net_out_bytes:
                    sample.epoca_contador = previous.epoca_contador or sample.epoca_contador
                    if minute - db_utc(previous.intervalo_at) == timedelta(minutes=1) and elapsed <= 120:
                        sample.net_in_delta, sample.net_out_delta = net_in - previous.net_in_bytes, net_out - previous.net_out_bytes
                        sample.duracion_observada_s = int(elapsed)
            sample.aplicacion_saludable = await observar_salud(health_request) if health_request else None
        sample.calidad = 'confirmada'
    except Exception:
        sample.calidad, sample.estado_observado = 'no_confirmada', None
        # No conservar métricas parciales como si fueran una observación válida.
        for field in ['cpu_usage_percent','ram_usage_mb','disk_usage_gb','net_in_bytes','net_out_bytes',
            'uptime_s','ram_max_mb','disk_max_bytes','vcpus_observadas','net_in_delta','net_out_delta','aplicacion_saludable']:
            setattr(sample, field, None)
        sample.duracion_observada_s = 0
        logger.warning('Observación no confirmada para servicio %s', service_id)
    await db.commit()
    await db.refresh(sample)
    return sample


async def capturar_todos_los_servicios(db: AsyncSession) -> dict:
    ids = list((await db.scalars(select(Servicio.id).where(Servicio.deleted_at.is_(None),
        Servicio.proxmox_vmid.is_not(None), Servicio.tipo == 'lxc'))).all())
    sessions = async_sessionmaker(db.bind, expire_on_commit=False)
    parallel = asyncio.Semaphore(4 if db.bind.dialect.name == 'postgresql' else 1)
    await db.commit()
    async def capture(service_id):
        async with parallel, sessions() as session:
            service = await session.get(Servicio, service_id)
            try:
                row = await capturar_snapshot_servicio(session, service)
                return bool(row and row.calidad == 'confirmada')
            except Exception:
                await session.rollback()
                logger.warning('Captura pendiente para servicio %s', service_id)
                return False
    results = await asyncio.gather(*(capture(service_id) for service_id in ids))
    return {'servicios_totales': len(ids), 'capturados': sum(results), 'errores': len(ids) - sum(results),
        'timestamp': clock.now().isoformat()}


async def obtener_historial(db: AsyncSession, servicio_id: int, limit: int = 60,
    *, desde=None, hasta=None, resolucion='minuto') -> list[MetricaSnapshot]:
    from sqlalchemy import BigInteger, cast, func
    conditions = [MetricaSnapshot.servicio_id == servicio_id]
    if desde is not None: conditions.append(MetricaSnapshot.timestamp >= desde)
    if hasta is not None: conditions.append(MetricaSnapshot.timestamp < hasta)
    limit = max(1, min(limit, 500))
    seconds = {'minuto': 0, 'hora': 3600, 'dia': 86400}.get(resolucion, 0)
    if resolucion == 'auto':
        import math
        span = ((hasta or clock.now()) - (desde or clock.now() - timedelta(days=90))).total_seconds()
        seconds = max(60, math.ceil(span / limit / 60) * 60)
    if seconds and desde is not None and hasta is not None and db.bind.dialect.name == 'postgresql':
        import math
        from sqlalchemy import text
        first, last = math.floor(desde.timestamp()/seconds), math.ceil(hasta.timestamp()/seconds)-1
        if 0 <= last-first < 5000:
            # Un seek por bloque usando ix_metrica_servicio_fecha, en lugar de
            # ordenar/rankear 129600 filas por servicio en cada consulta90d.
            # La muestra es real, conserva todos sus límites y nunca rellena
            # huecos. Acotar bloques evita expandir rangos arbitrarios enormes.
            statement = text('''SELECT sample.*
                FROM generate_series(:last_bucket, :first_bucket, -1) AS blocks(bucket)
                CROSS JOIN LATERAL (
                    SELECT m.* FROM metricas_snapshots m
                    WHERE m.servicio_id=:service_id
                      AND m.timestamp >= GREATEST(CAST(:since AS timestamptz), to_timestamp(blocks.bucket * CAST(:seconds AS bigint)))
                      AND m.timestamp < LEAST(CAST(:until AS timestamptz), to_timestamp((blocks.bucket+1) * CAST(:seconds AS bigint)))
                    ORDER BY m.timestamp DESC, m.id DESC LIMIT 1
                ) sample
                ORDER BY sample.timestamp DESC, sample.id DESC LIMIT :point_limit''')
            result = await db.scalars(select(MetricaSnapshot).from_statement(statement), {
                'last_bucket':last,'first_bucket':first,'service_id':servicio_id,
                'since':desde,'until':hasta,'seconds':seconds,'point_limit':limit})
            return list(reversed(result.all()))
    query = select(MetricaSnapshot)
    if seconds:
        # Seleccionar una muestra real por bloque, sin combinar sus límites con
        # consumos de otra fecha ni presentarla como cobertura del bloque entero.
        epoch = (func.extract('epoch', MetricaSnapshot.timestamp) if db.bind.dialect.name == 'postgresql'
            else cast(func.strftime('%s', MetricaSnapshot.timestamp), BigInteger))
        bucket = (func.floor(epoch / seconds) if db.bind.dialect.name == 'postgresql' else cast(epoch / seconds, BigInteger))
        ranked = select(MetricaSnapshot.id.label('snapshot_id'), func.row_number().over(
            partition_by=bucket,
            order_by=[MetricaSnapshot.timestamp.desc(), MetricaSnapshot.id.desc()]).label('position'))            .where(*conditions).subquery()
        query = query.join(ranked, ranked.c.snapshot_id == MetricaSnapshot.id).where(ranked.c.position == 1)
    else:
        query = query.where(*conditions)
    result = await db.scalars(query.order_by(desc(MetricaSnapshot.timestamp), desc(MetricaSnapshot.id)).limit(limit))
    return list(reversed(result.all()))


async def obtener_ultimo_snapshot(db: AsyncSession, servicio_id: int) -> MetricaSnapshot | None:
    return await db.scalar(select(MetricaSnapshot).where(MetricaSnapshot.servicio_id == servicio_id)
        .order_by(desc(MetricaSnapshot.timestamp), desc(MetricaSnapshot.id)).limit(1))

# Fachada compartida por routers, CLI de prueba y trabajo diario.
from app.services.resumen_metricas_service import agregar_dia, agregar_y_purgar, purgar_detalle, consultar_consumo  # noqa: E402,F401
