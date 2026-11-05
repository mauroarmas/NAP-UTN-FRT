from datetime import timedelta

import pytest
from sqlalchemy import insert, select

from app.models.metrica import MetricaSnapshot
from app.models.notificacion import Notificacion
from app.services import inactividad_service as inactivity
from app.utils.clock import clock
from tests.test_metricas_intervalos_009 import measured  # noqa: F401
from tests.capacity_helpers import perfil_capacidad  # noqa: F401


async def window(db, case, *, count=8064, cpu=1, traffic=0, age=1, legacy=False):
    end = case.now.replace(second=0) - timedelta(minutes=age)
    rows = []
    for i in range(count):
        at = end - timedelta(minutes=count - i - 1)
        rows.append(dict(servicio_id=case.service.id, timestamp=at,
            intervalo_at=None if legacy else at, calidad='confirmada', estado_observado='running',
            cpu_usage_percent=cpu if i == 0 else 1, ram_usage_mb=128,
            net_in_bytes=2**54 + 1, net_out_bytes=2**54 + 3,
            net_in_delta=traffic if i == 0 else 0, net_out_delta=0, duracion_observada_s=60))
    await db.execute(insert(MetricaSnapshot), rows)
    await db.commit()


async def test_constant_large_counters_are_not_historical_traffic(db, measured):
    await window(db, measured)
    result = await inactivity.evaluar_actividad(db, measured.service)
    assert result['inactivo'] is True
    assert result['cobertura'] == pytest.approx(0.8)
    assert result['trafico_bytes'] == 0 and result['esperadas'] == 10080


@pytest.mark.parametrize('case', ['coverage', 'cpu_boundary', 'traffic_boundary', 'legacy', 'stale'])
async def test_unknown_or_active_window_does_not_authorize_pause(db, measured, case):
    kwargs = {'coverage': {'count': 8063}, 'cpu_boundary': {'cpu': 5},
        'traffic_boundary': {'traffic': 1_000_000}, 'legacy': {'legacy': True}, 'stale': {'age': 60}}[case]
    await window(db, measured, **kwargs)
    assert (await inactivity.evaluar_actividad(db, measured.service))['inactivo'] is False


async def test_notice_and_48h_grace_are_durable_and_do_not_stop_the_guest(db, measured, proxmox):
    await window(db, measured)
    await inactivity.evaluar_inactividad(db)
    await inactivity.evaluar_inactividad(db)
    await db.refresh(measured.service)
    assert measured.service.pausa_programada_at - measured.service.aviso_pausa_at == timedelta(hours=48)
    entries = list((await db.scalars(select(Notificacion))).all())
    assert entries and len({(n.evento_clave,n.destinatario_normalizado,n.canal) for n in entries}) == len(entries)
    assert measured.service.estado.value == 'running'
    assert not proxmox.detenidos


async def test_lost_observation_cancels_pending_pause_and_notifies(db, measured):
    measured.service.aviso_pausa_at = measured.now.replace(tzinfo=None) - timedelta(days=3)
    measured.service.pausa_programada_at = measured.now.replace(tzinfo=None) - timedelta(days=1)
    await db.commit()
    result = await inactivity.evaluar_inactividad(db)
    assert measured.service.id in result['cancelados']
    assert measured.service.pausa_programada_at is None
    assert (await db.scalars(select(Notificacion))).first() is not None
