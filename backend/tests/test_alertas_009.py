"""US7: evidencia negativa consecutiva, carga sostenida y avisos durables."""
from datetime import timedelta
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.metrica import MetricaSnapshot
from app.models.notificacion import Notificacion
from app.models.servicio import EstadoServicio
from app.services import notificacion_service
from app.utils.clock import clock
from tests import factories
from tests.capacity_helpers import materializado, perfil_capacidad  # noqa: F401


@pytest_asyncio.fixture
async def case(db, proxmox, monkeypatch, perfil_capacidad, catedra, usuario_catedra, template):
    value = SimpleNamespace(start=clock.now().replace(second=0, microsecond=0))
    value.now = value.start
    monkeypatch.setattr(clock, 'now', lambda: value.now)
    value.service, _ = await materializado(db, proxmox, catedra, usuario_catedra, template)
    value.service.estado = EstadoServicio.RUNNING
    await db.commit()

    async def add(minute, *, second=0, state='running', quality='confirmada', health=True, cpu=10.0, ram=100):
        when = value.start + timedelta(minutes=minute, seconds=second)
        row = MetricaSnapshot(servicio_id=value.service.id, timestamp=when,
            intervalo_at=when.replace(second=0), estado_observado=state, calidad=quality,
            aplicacion_saludable=health, cpu_usage_percent=cpu, ram_usage_mb=ram,
            ram_max_mb=1024, vcpus_observadas=2, disk_usage_gb=1, disk_max_bytes=10 * 1024**3,
            uptime_s=1000 + minute * 60, epoca_contador='alert-test-epoch',
            net_in_bytes=minute * 100, net_out_bytes=minute * 100,
            net_in_delta=100, net_out_delta=100, duracion_observada_s=60)
        db.add(row)
        value.now = max(value.now, when + timedelta(seconds=1))
        await db.commit()
        return row
    value.add = add
    return value


async def evaluate(db):
    from app.services.alerta_service import evaluar_alertas
    await evaluar_alertas(db)


async def incidents(db, *, kind=None):
    from app.models.incidente import Incidente
    query = select(Incidente).order_by(Incidente.abierto_at)
    if kind:
        query = query.where(Incidente.tipo == kind)
    return list((await db.scalars(query)).all())


@pytest.mark.parametrize('negative', ['stopped', 'application_failed'])
async def test_down_requires_two_confirmed_negatives_and_opens_only_once(db, case, negative):
    kwargs = {'state': 'stopped', 'health': None} if negative == 'stopped' else {'health': False}
    await case.add(0, **kwargs)
    await evaluate(db)
    assert not await incidents(db)
    await case.add(1, **kwargs)
    for _ in range(3):
        await evaluate(db)
    rows = await incidents(db, kind='caida')
    assert len(rows) == 1 and rows[0].estado == 'abierto'
    assert rows[0].regla_version and rows[0].resuelto_at is None
    notices = list((await db.scalars(select(Notificacion))).all())
    assert notices and len({(n.evento_clave, n.destinatario_normalizado, n.canal) for n in notices}) == len(notices)


async def test_two_observations_less_than_one_minute_do_not_open_down(db, case):
    await case.add(0, second=30, health=False)
    await case.add(1, second=29, health=False)
    await evaluate(db)
    assert not await incidents(db)


async def test_unknown_observation_breaks_negative_sequence_and_never_recovers_an_open_incident(db, case):
    await case.add(0, health=False)
    await case.add(1, state=None, quality='no_confirmada', health=None, cpu=None, ram=None)
    await case.add(2, health=False)
    await evaluate(db)
    assert not await incidents(db)
    await case.add(3, health=False)
    await evaluate(db)
    await case.add(4, state=None, quality='no_confirmada', health=None, cpu=None, ram=None)
    await evaluate(db)
    assert (await incidents(db))[0].estado == 'abierto'


@pytest.mark.parametrize('kind', ['cpu_sostenida', 'ram_sostenida'])
async def test_load_requires_fifteen_complete_minutes_not_fifteen_retries(db, case, kind):
    kwargs = {'cpu': 95.0} if kind == 'cpu_sostenida' else {'ram': 950}
    for minute in range(15):
        await case.add(minute, **kwargs)
    await evaluate(db)
    assert not await incidents(db, kind=kind)
    await case.add(15, **kwargs)
    await evaluate(db)
    assert len(await incidents(db, kind=kind)) == 1
    await evaluate(db)
    assert len(await incidents(db, kind=kind)) == 1


async def test_missing_or_normal_minute_prevents_claiming_sustained_load(db, case):
    for minute in range(16):
        kwargs = {'quality': 'no_confirmada', 'cpu': None, 'health': None} if minute == 8 else {'cpu': 95.0}
        await case.add(minute, **kwargs)
    await evaluate(db)
    assert not await incidents(db, kind='cpu_sostenida')


@pytest.mark.parametrize('kind', ['cpu_sostenida', 'ram_sostenida'])
async def test_ninety_percent_is_not_strictly_above_the_threshold(db, case, kind):
    kwargs = {'cpu': 90.0} if kind == 'cpu_sostenida' else {'ram': 921.6}
    for minute in range(16):
        await case.add(minute, **kwargs)
    await evaluate(db)
    assert not await incidents(db, kind=kind)


async def test_recovery_needs_two_normal_minutes_and_is_not_repeated(db, case):
    await case.add(0, health=False)
    await case.add(1, health=False)
    await evaluate(db)
    await case.add(2)
    await evaluate(db)
    assert (await incidents(db))[0].estado == 'abierto'
    await case.add(3)
    for _ in range(3):
        await evaluate(db)
    row = (await incidents(db))[0]
    assert row.estado == 'resuelto' and row.resuelto_at is not None
    notices = list((await db.scalars(select(Notificacion))).all())
    assert len({n.evento_clave for n in notices}) == 2  # apertura y recuperación


async def test_expected_pause_does_not_look_like_an_unexpected_outage(db, case):
    case.service.estado = EstadoServicio.PAUSED
    await db.commit()
    await case.add(0, state='stopped', health=None)
    await case.add(1, state='stopped', health=None)
    await evaluate(db)
    assert not await incidents(db, kind='caida')


async def test_uncertain_operation_has_one_incident_until_a_confirmed_outcome(db, case):
    from app.models.operacion_infraestructura import OperacionInfraestructura
    op = OperacionInfraestructura(servicio_id=case.service.id, tipo='detener', estado='incierta',
        actor_tipo='sistema', actor_id_normalizado='prueba-alertas', idempotency_key='prueba-incierta',
        request_hash='a' * 64, contexto_seguro={})
    db.add(op)
    await db.commit()
    await evaluate(db)
    await evaluate(db)
    assert len(await incidents(db, kind='operacion_incierta')) == 1
    op.estado = 'confirmada'
    case.now += timedelta(seconds=1)
    await db.commit()
    await evaluate(db)
    assert (await incidents(db, kind='operacion_incierta'))[0].estado == 'resuelto'


async def test_overdue_service_is_recovered_only_after_pause_is_confirmed(db, case):
    case.now += timedelta(days=60)
    await evaluate(db)
    assert (await incidents(db, kind='vencimiento_no_aplicado'))[0].estado == 'abierto'
    case.service.estado = EstadoServicio.PAUSED
    case.now += timedelta(seconds=1)
    await db.commit()
    await evaluate(db)
    assert (await incidents(db, kind='vencimiento_no_aplicado'))[0].estado == 'resuelto'


async def test_old_recipient_is_revalidated_when_email_is_sent(db, case, catedra, usuario_catedra):
    owner_id, owner_email = usuario_catedra.id, usuario_catedra.email
    await case.add(0, health=False)
    await case.add(1, health=False)
    await evaluate(db)
    pending = list((await db.scalars(select(Notificacion).where(
        Notificacion.destinatario_usuario_id == owner_id, Notificacion.canal == 'email'))).all())
    assert len(pending) == 1
    successor = await factories.crear_usuario(db, 'nuevo-titular-alertas')
    catedra.titular_id = successor.id  # estado posterior a una reasignación ya confirmada
    await db.commit()
    recipients = []
    def sender(addresses, *args, **kwargs):
        recipients.extend(addresses)
    for _ in range(10):
        if not await notificacion_service.procesar_uno(db, sender=sender):
            break
    await db.refresh(pending[0])
    assert pending[0].estado == 'cancelada' and owner_email not in recipients


async def test_smtp_failure_does_not_roll_back_the_incident_or_record_secrets(db, case, usuario_catedra, caplog):
    owner_id = usuario_catedra.id
    await case.add(0, health=False)
    await case.add(1, health=False)
    await evaluate(db)
    def sender(*args, **kwargs):
        raise RuntimeError('private-smtp-value-must-not-be-recorded')
    for _ in range(10):
        if not await notificacion_service.procesar_uno(db, sender=sender):
            break
    notices = list((await db.scalars(select(Notificacion).where(
        Notificacion.destinatario_usuario_id == owner_id, Notificacion.canal == 'email'))).all())
    assert len(notices) == 1 and notices[0].estado == 'fallida'
    assert notices[0].ultimo_error == 'entrega_no_confirmada'
    assert 'private-smtp-value' not in caplog.text
    rows = await incidents(db, kind='caida')
    assert len(rows) == 1 and rows[0].estado == 'abierto'
