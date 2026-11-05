"""US7: agregados durables sin inventar cobertura ni perder historia al purgar."""
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.models.metrica import MetricaSnapshot
from app.models.servicio import EstadoServicio
from app.models.servicio_historial import ServicioHistorial
from app.services import metricas_service as metrics
from app.utils.clock import clock
from tests.capacity_helpers import materializado, perfil_capacidad  # noqa: F401

ZONE = 'America/Argentina/Tucuman'
DAY = date(2026, 7, 1)


@pytest_asyncio.fixture
async def consumption(db, proxmox, monkeypatch, perfil_capacidad, catedra, usuario_catedra, template):
    start = datetime.combine(DAY, datetime.min.time(), ZoneInfo(ZONE)).astimezone(timezone.utc)
    case = SimpleNamespace(start=start, now=start + timedelta(days=100))
    monkeypatch.setattr(clock, 'now', lambda: case.now)
    case.service, _ = await materializado(db, proxmox, catedra, usuario_catedra, template)
    case.service.estado = EstadoServicio.RUNNING
    db.add(ServicioHistorial(servicio_id=case.service.id, estado_anterior='stopped',
        estado_nuevo='running', created_at=start.replace(tzinfo=None), evento_clave='historical-allocation',
        actor_tipo='sistema', decision_metadata={'asignacion': {'vcpus': 2, 'ram_mb': 1024, 'disk_gb': 8},
            'catedra_id': catedra.id}))
    await db.commit()

    async def add(minute, *, second=0, duration=60, quality='confirmada', state='running',
                  cpu=20.0, ram=128, traffic=100, epoch='historical-epoch'):
        at = start + timedelta(minutes=minute, seconds=second)
        row = MetricaSnapshot(servicio_id=case.service.id, timestamp=at,
            intervalo_at=at.replace(second=0, microsecond=0), calidad=quality,
            estado_observado=state, aplicacion_saludable=True if state == 'running' else None,
            cpu_usage_percent=cpu, ram_usage_mb=ram, disk_usage_gb=1,
            ram_max_mb=1024, disk_max_bytes=8 * 1024**3, vcpus_observadas=2,
            uptime_s=10000 + minute * 60 + second, epoca_contador=epoch,
            net_in_bytes=2**54 + max(0, minute) * 100, net_out_bytes=2**54 + max(0, minute) * 200,
            net_in_delta=traffic if duration else None, net_out_delta=traffic * 2 if duration else None,
            duracion_observada_s=duration)
        db.add(row)
        await db.commit()
        return row
    case.add = add
    return case


async def aggregate(db, case, *, day=DAY, zone=ZONE):
    return await metrics.agregar_dia(db, servicio_id=case.service.id, fecha_local=day, zona_horaria=zone)


async def test_daily_upsert_is_idempotent_and_uses_deltas_not_cumulative_counters(db, consumption):
    await consumption.add(0, duration=0)
    await consumption.add(1)
    await consumption.add(2)
    await aggregate(db, consumption)
    result = await aggregate(db, consumption)
    from app.models.metricas_resumen import MetricaResumenDiario
    assert await db.scalar(select(func.count()).select_from(MetricaResumenDiario)) == 1
    assert (result.servicio_id, result.fecha_local, result.zona_horaria) == (consumption.service.id, DAY, ZONE)
    assert result.intervalos_esperados == 1440 and result.intervalos_validos == 3
    assert result.segundos_observados == 120 and result.segundos_running == 120
    assert result.cpu_integral == pytest.approx(20 * 120)
    assert result.ram_integral_mb_s == 128 * 120
    assert result.trafico_in_bytes == 200 and result.trafico_out_bytes == 400
    assert result.periodo_cerrado is True


async def test_integrals_retain_duration_denominators_instead_of_averaging_averages(db, consumption):
    await consumption.add(0, second=10, duration=0)
    await consumption.add(1, duration=50, cpu=10, ram=100)
    await consumption.add(2, second=10, duration=70, cpu=90, ram=200)
    result = await aggregate(db, consumption)
    assert result.segundos_observados == 120
    assert result.cpu_integral == pytest.approx(10 * 50 + 90 * 70)
    assert result.ram_integral_mb_s == 100 * 50 + 200 * 70
    assert result.cpu_max == 90 and result.ram_max_mb == 200
    assert result.disk_max_bytes == 8 * 1024**3


async def test_unknown_and_missing_minutes_do_not_inflate_observed_time_or_coverage(db, consumption):
    await consumption.add(0, duration=0)
    await consumption.add(1)
    await consumption.add(2, duration=0, quality='no_confirmada', state=None, cpu=None, ram=None)
    await consumption.add(4, duration=0)
    result = await aggregate(db, consumption)
    assert result.intervalos_validos == 3
    assert result.segundos_observados == 60 and result.cpu_integral == 20 * 60
    assert result.trafico_in_bytes == 100 and result.segundos_running == 60


async def test_reset_never_attributes_counter_totals_as_traffic(db, consumption):
    await consumption.add(0, duration=0)
    await consumption.add(1)
    await consumption.add(2, duration=0, epoch='after-reboot')
    result = await aggregate(db, consumption)
    assert result.trafico_in_bytes == 100 and result.trafico_out_bytes == 200
    assert result.segundos_observados == 60


async def test_boundary_delta_counted_once_and_duration_clipped_to_local_day(db, consumption):
    # Bytes del intervalo indivisible se atribuyen al día de la muestra final.
    await consumption.add(-1, second=30, duration=0)
    await consumption.add(0, second=30, duration=60, traffic=120)
    before = await aggregate(db, consumption, day=DAY - timedelta(days=1))
    today = await aggregate(db, consumption)
    assert before.trafico_in_bytes == 0 and today.trafico_in_bytes == 120
    assert today.segundos_observados == 30 and today.cpu_integral == 20 * 30


@pytest.mark.parametrize('day,expected', [(date(2026, 3, 8), 1380), (date(2026, 11, 1), 1500)])
async def test_expected_intervals_use_actual_local_day_across_dst(db, consumption, day, expected):
    consumption.now = datetime(2027, 1, 1, tzinfo=timezone.utc)
    result = await aggregate(db, consumption, day=day, zone='America/New_York')
    assert result.intervalos_esperados == expected
    assert result.intervalos_validos == 0 and result.segundos_observados == 0


async def test_current_day_remains_open_and_cannot_authorize_purge(db, consumption):
    consumption.now = consumption.start + timedelta(hours=12)
    await consumption.add(1)
    result = await aggregate(db, consumption)
    assert result.periodo_cerrado is False


async def test_purge_without_closed_summary_retains_detail(db, consumption):
    sample = await consumption.add(1)
    await metrics.purgar_detalle(db)
    assert await db.get(MetricaSnapshot, sample.id) is not None


async def test_purge_preserves_summary_and_edge_needed_for_next_day(db, consumption):
    await consumption.add(0, duration=0)
    await consumption.add(1)
    edge = await consumption.add(1439, duration=0)
    following = await consumption.add(1440)
    summary = await aggregate(db, consumption)
    expected = (summary.cpu_integral, summary.intervalos_validos, summary.trafico_in_bytes)
    await metrics.purgar_detalle(db)
    await db.commit()
    remaining = set((await db.scalars(select(MetricaSnapshot.id))).all())
    assert edge.id in remaining and following.id in remaining and len(remaining) == 2
    again = await aggregate(db, consumption)
    assert (again.cpu_integral, again.intervalos_validos, again.trafico_in_bytes) == expected


async def test_allocation_time_uses_historical_resources_not_changed_template(db, consumption, template):
    await consumption.add(0, duration=0)
    await consumption.add(1)
    template.default_vcpus = 16
    template.default_ram_mb = 32000
    consumption.service.vcpus_asignados = 8
    consumption.service.ram_asignada_mb = 8192
    await db.commit()
    result = await aggregate(db, consumption)
    assert result.vcpu_segundos == 2 * 60
    assert result.ram_asignada_mb_segundos == 1024 * 60
    assert result.disk_asignado_byte_segundos == 8 * 1024**3 * 60


async def test_allocation_change_inside_observed_interval_splits_resource_time(db, consumption):
    await consumption.add(0, duration=0)
    await consumption.add(1)
    db.add(ServicioHistorial(servicio_id=consumption.service.id, estado_anterior='running', estado_nuevo='running',
        created_at=(consumption.start + timedelta(seconds=30)).replace(tzinfo=None),
        evento_clave='confirmed-allocation-change', actor_tipo='sistema',
        decision_metadata={'asignacion': {'vcpus': 4, 'ram_mb': 2048, 'disk_gb': 16}}))
    await db.commit()
    result = await aggregate(db, consumption)
    assert result.vcpu_segundos == 2 * 30 + 4 * 30
    assert result.ram_asignada_mb_segundos == 1024 * 30 + 2048 * 30


async def test_missing_historical_assignment_remains_unknown(db, consumption):
    # Otro servicio sin eventos de asignación: no inferir de su catálogo actual.
    from tests import factories
    service = await factories.crear_servicio(db, consumption.service.catedra_id, consumption.service.template_id,
        proxmox_vmid=None)
    consumption.service = service
    await consumption.add(0, duration=0)
    await consumption.add(1)
    result = await aggregate(db, consumption)
    assert result.segundos_observados == 60
    assert result.vcpu_segundos is None and result.disk_asignado_byte_segundos is None


async def test_consumption_survives_soft_delete_and_owner_reassignment(db, consumption, catedra):
    from tests import factories
    await consumption.add(0, duration=0)
    await consumption.add(1)
    await aggregate(db, consumption)
    new_owner = await factories.crear_usuario(db, 'nuevo-titular-resumen')
    catedra.titular_id = new_owner.id
    consumption.service.deleted_at = consumption.now.replace(tzinfo=None)
    await db.commit()
    result = await metrics.consultar_consumo(db, catedra_id=catedra.id, desde=DAY, hasta=DAY + timedelta(days=1))
    assert len(result) == 1 and result[0].catedra_id == catedra.id
    assert result[0].servicio_id == consumption.service.id and result[0].vcpu_segundos == 120


async def test_failed_aggregation_does_not_purge_detail(db, consumption, monkeypatch):
    sample = await consumption.add(1)
    async def fail(*args, **kwargs):
        raise RuntimeError('fallo de agregación inducido')
    monkeypatch.setattr(metrics, 'agregar_dia', fail, raising=False)
    with pytest.raises(RuntimeError):
        await metrics.agregar_y_purgar(db)
    assert await db.get(MetricaSnapshot, sample.id) is not None
