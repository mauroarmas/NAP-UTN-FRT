"""US7: observaciones por minuto, sin convertir silencio o resets en cero uso."""
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import BigInteger, func, select

from app.models.metrica import MetricaSnapshot
from app.models.servicio import EstadoServicio
from app.services import metricas_service as metrics
from app.utils.clock import clock, db_utc
from tests.capacity_helpers import materializado, perfil_capacidad  # noqa: F401


@pytest_asyncio.fixture
async def measured(db, proxmox, monkeypatch, perfil_capacidad, catedra, usuario_catedra, template):
    state = SimpleNamespace(now=clock.now().replace(second=10, microsecond=0), calls=[])
    monkeypatch.setattr(clock, 'now', lambda: state.now)
    state.service, _ = await materializado(db, proxmox, catedra, usuario_catedra, template)
    state.service.estado = EstadoServicio.RUNNING
    await db.commit()
    proxmox.estados[int(state.service.proxmox_vmid)] = 'running'
    proxmox.recursos[-1]['status'] = 'running'
    state.payload = {'status': 'running', 'cpu': 0.25, 'cpus': 4,
        'mem': 128 * 1024**2, 'maxmem': 2048 * 1024**2,
        'disk': 1024**3, 'maxdisk': 8 * 1024**3 - 4096,
        'netin': 2**54 + 1, 'netout': 2**54 + 3, 'uptime': 1000}

    def read(node, vmid):
        state.calls.append((node, vmid))
        return deepcopy(state.payload)
    monkeypatch.setattr(proxmox, 'get_lxc_status', read)
    return state


def test_network_columns_retain_bigint_precision():
    for name in ('net_in_bytes', 'net_out_bytes'):
        assert isinstance(MetricaSnapshot.__table__.c[name].type, BigInteger)


async def test_first_observation_has_exact_counters_and_limits_from_that_sample(db, measured):
    sample = await metrics.capturar_snapshot_servicio(db, measured.service)
    assert sample.net_in_bytes == 2**54 + 1 and type(sample.net_in_bytes) is int
    assert sample.net_out_bytes == 2**54 + 3 and type(sample.net_out_bytes) is int
    assert db_utc(sample.timestamp) == measured.now
    assert db_utc(sample.intervalo_at) == measured.now.replace(second=0)
    assert sample.calidad == 'confirmada' and sample.estado_observado == 'running'
    assert sample.cpu_usage_percent == 25.0  # PVE ya entrega la fracción normalizada.
    assert sample.ram_max_mb == 2048 and sample.disk_max_bytes == 8 * 1024**3 - 4096
    assert sample.vcpus_observadas == 4 and sample.uptime_s == 1000
    assert sample.net_in_delta is None and sample.net_out_delta is None
    assert sample.duracion_observada_s == 0 and sample.epoca_contador


async def test_manual_and_periodic_calls_share_one_minute_without_extra_coverage(db, measured):
    first = await metrics.capturar_snapshot_servicio(db, measured.service)
    measured.now += timedelta(seconds=20)
    measured.payload['cpu'] = 0.99
    second = await metrics.capturar_snapshot_servicio(db, measured.service)
    assert second.id == first.id
    assert await db.scalar(select(func.count()).select_from(MetricaSnapshot)) == 1
    assert len(measured.calls) == 1 and second.cpu_usage_percent == 25.0


async def test_next_minute_uses_counter_differences_not_total_traffic(db, measured):
    first = await metrics.capturar_snapshot_servicio(db, measured.service)
    measured.now += timedelta(minutes=1)
    measured.payload.update(netin=2**54 + 101, netout=2**54 + 503, uptime=1060)
    second = await metrics.capturar_snapshot_servicio(db, measured.service)
    assert second.net_in_delta == 100 and second.net_out_delta == 500
    assert second.epoca_contador == first.epoca_contador
    assert second.duracion_observada_s == 60


@pytest.mark.parametrize('reset', ['counter', 'uptime', 'new_boot_with_higher_uptime'])
async def test_reset_starts_a_new_epoch_without_a_negative_or_invented_delta(db, measured, reset):
    if reset == 'new_boot_with_higher_uptime':
        measured.payload['uptime'] = 10
    first = await metrics.capturar_snapshot_servicio(db, measured.service)
    measured.now += timedelta(minutes=1)
    measured.payload.update(netin=2**54 + 101, netout=2**54 + 103, uptime=1060)
    if reset == 'counter':
        measured.payload['netin'] = 7
    elif reset == 'uptime':
        measured.payload['uptime'] = 3
    else:
        # Un reboot puede producir uptime mayor al anterior, pero incompatible
        # con los sesenta segundos transcurridos: no basta comparar "menor".
        measured.payload['uptime'] = 20
    second = await metrics.capturar_snapshot_servicio(db, measured.service)
    assert second.epoca_contador != first.epoca_contador
    assert second.net_in_delta is None and second.net_out_delta is None
    assert second.duracion_observada_s == 0


async def test_gap_does_not_fill_missing_minutes_or_attribute_their_traffic(db, measured):
    first = await metrics.capturar_snapshot_servicio(db, measured.service)
    measured.now += timedelta(minutes=3)
    measured.payload.update(netin=2**54 + 1001, netout=2**54 + 1003, uptime=1180)
    second = await metrics.capturar_snapshot_servicio(db, measured.service)
    assert await db.scalar(select(func.count()).select_from(MetricaSnapshot)) == 2
    assert second.epoca_contador == first.epoca_contador
    assert second.net_in_delta is None and second.net_out_delta is None
    assert second.duracion_observada_s == 0


async def test_transport_failure_is_unconfirmed_and_never_logged_as_a_secret(db, measured, proxmox, monkeypatch, caplog):
    def fail(*args):
        raise TimeoutError('transport-private-should-not-log')
    monkeypatch.setattr(proxmox, 'get_lxc_status', fail)
    sample = await metrics.capturar_snapshot_servicio(db, measured.service)
    assert sample is not None and sample.calidad == 'no_confirmada'
    assert sample.estado_observado is None and sample.cpu_usage_percent is None
    assert sample.ram_usage_mb is None and sample.net_in_delta is None
    assert 'transport-private-should-not-log' not in caplog.text
    assert measured.service.estado == EstadoServicio.RUNNING


async def test_stopped_is_an_observation_distinct_from_a_transport_failure(db, measured):
    measured.payload = {'status': 'stopped'}
    sample = await metrics.capturar_snapshot_servicio(db, measured.service)
    assert sample is not None
    assert sample.estado_observado == 'stopped' and sample.calidad == 'confirmada'
    assert sample.net_in_delta is None and sample.duracion_observada_s == 0


@pytest.mark.parametrize('counter', [-1, 2**63, 12.5, True, None])
async def test_invalid_counters_do_not_become_zero_or_overflow_the_database(db, measured, counter):
    measured.payload['netin'] = counter
    sample = await metrics.capturar_snapshot_servicio(db, measured.service)
    assert sample.calidad == 'no_confirmada'
    assert sample.net_in_delta is None and sample.net_in_bytes is None


async def test_missing_limits_are_not_taken_from_a_different_observation(db, measured):
    for key in ('maxmem', 'maxdisk', 'cpus'):
        measured.payload.pop(key)
    sample = await metrics.capturar_snapshot_servicio(db, measured.service)
    assert sample.ram_max_mb is None and sample.disk_max_bytes is None
    assert sample.vcpus_observadas is None


async def test_foreign_identity_does_not_allow_reading_telemetry(db, measured, proxmox):
    proxmox.configuraciones[('pve1', int(measured.service.proxmox_vmid))]['description'] = 'sin marca propia'
    sample = await metrics.capturar_snapshot_servicio(db, measured.service)
    assert sample.calidad == 'no_confirmada' and sample.cpu_usage_percent is None
    assert measured.calls == []


@pytest.mark.parametrize('ready', [True, False])
async def test_application_health_requires_confirmed_identity_and_completed_bootstrap(monkeypatch, ready):
    from tests.test_guest_runner_client import request
    from app.services.guest_runner_client import GuestRunnerClient
    value = request('inspect')
    async def execute(self, sent):
        assert sent['action'] == 'inspect' and 'secrets' not in sent
        return {**{k: sent[k] for k in ['protocol','operation_id','action','resource_uuid']},
            'status': 'succeeded' if ready else 'pending', 'phase': 'verified',
            'observed_at': clock.now().isoformat(), 'identity_verified': True,
            'result': {'ready': ready, 'bootstrap_completed': True}}
    monkeypatch.setattr(GuestRunnerClient, 'execute', execute)
    assert await metrics.observar_salud(value) is ready


async def test_application_probe_timeout_is_unknown_and_does_not_expose_request(monkeypatch, caplog):
    from tests.test_guest_runner_client import request
    from app.services.guest_runner_client import GuestRunnerClient
    async def execute(self, sent):
        raise TimeoutError('private-transport-error')
    monkeypatch.setattr(GuestRunnerClient, 'execute', execute)
    assert await metrics.observar_salud(request('inspect')) is None
    assert 'private-transport-error' not in caplog.text


async def test_recurring_health_request_does_not_grow_runner_deduplication_state(db, measured):
    from app.models.identidad_infraestructura import IdentidadInfraestructura
    identity = await db.get(IdentidadInfraestructura, measured.service.identidad_infraestructura_id)
    identity.definition_sha256, identity.bundle_sha256 = 'a' * 64, 'b' * 64
    measured.service.asignacion_snapshot = {'definition_key': 'linux-lab', 'definition_version': '1.0.0',
        'definition_sha256': identity.definition_sha256, 'bundle_sha256': identity.bundle_sha256}
    measured.service.acceso_metadata = {'preparacion_id': 'fixture-preparation',
        'bootstrap_parameters': {'display_name': 'Laboratorio'}, 'bootstrap_network_profile_id': 'test-network'}
    first = metrics._health_request(identity, measured.service)
    measured.now += timedelta(minutes=1)
    second = metrics._health_request(identity, measured.service)
    assert first == second and first['action'] == 'inspect' and 'secrets' not in first


async def test_gets_only_read_stored_samples_and_keep_integer_counters(db, measured, client, auth_admin, monkeypatch):
    sample = await metrics.capturar_snapshot_servicio(db, measured.service)

    def forbidden(*args, **kwargs):
        raise AssertionError('Un GET no consulta PVE ni captura observaciones')
    monkeypatch.setattr('app.services.proxmox_client.get_proxmox_client', forbidden)
    monkeypatch.setattr('app.services.proxmox_client.get_proxmox_factory', forbidden)
    monkeypatch.setattr('app.routers.metricas.capturar_snapshot_servicio', forbidden)
    monkeypatch.setattr('app.routers.metricas.capturar_todos_los_servicios', forbidden)
    for suffix in ('/resumen', f'/{measured.service.id}/historial', f'/{measured.service.id}/ultimo'):
        response = await client.get('/metricas' + suffix, headers=auth_admin)
        assert response.status_code == 200, response.text
        if suffix == '/resumen':
            stored = response.json()[0]['ultimo_snapshot']
        elif suffix.endswith('/historial'):
            stored = response.json()[0]
        else:
            stored = response.json()
        assert stored['id'] == sample.id and type(stored['net_in_bytes']) is int
        assert stored['net_in_bytes'] == 2**54 + 1
        assert stored['ram_max_mb'] == 2048 and stored['disk_max_bytes'] == 8 * 1024**3 - 4096
