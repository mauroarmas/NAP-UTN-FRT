from datetime import date, timedelta
from sqlalchemy import insert

from app.models.metrica import MetricaSnapshot
from app.services.metricas_service import agregar_dia, obtener_historial
from tests.capacity_helpers import perfil_capacidad  # noqa: F401
from tests.test_metricas_intervalos_009 import measured  # noqa: F401


async def test_daily_traffic_can_exceed_bigint_without_losing_one_byte(db, measured, client, auth_admin):
    start = measured.now.replace(hour=3, minute=0, second=0) - timedelta(days=1)
    big = 2**62 + 1
    rows = []
    for i in range(6):
        at = start + timedelta(minutes=i)
        delta = big if i % 2 else None
        rows.append(dict(servicio_id=measured.service.id, timestamp=at, intervalo_at=at,
            calidad='confirmada', estado_observado='running', cpu_usage_percent=1, ram_usage_mb=128,
            net_in_bytes=big if delta else 0, net_out_bytes=0, net_in_delta=delta,
            net_out_delta=0 if delta else None, duracion_observada_s=60 if delta else 0,
            epoca_contador=f'precision-epoch-{i//2}'))
    await db.execute(insert(MetricaSnapshot), rows)
    await db.commit()
    day = start.date()
    summary = await agregar_dia(db, servicio_id=measured.service.id, fecha_local=day,
        zona_horaria='America/Argentina/Tucuman')
    assert summary.trafico_in_bytes == 3 * big
    await db.commit()
    response = await client.get('/metricas/consumo', params={'catedra_id': measured.service.catedra_id,
        'desde': day.isoformat(), 'hasta': (day + timedelta(days=1)).isoformat()}, headers=auth_admin)
    assert response.status_code == 200
    assert response.json()[0]['trafico_in_bytes'] == 3 * big
    assert type(response.json()[0]['trafico_in_bytes']) is int


async def test_hourly_selection_uses_hour_boundaries_instead_of_rounding_timestamps(db, measured):
    start = measured.now.replace(hour=3, minute=0, second=0) - timedelta(days=1)
    for minutes in [40,70]:
        at = start + timedelta(minutes=minutes)
        db.add(MetricaSnapshot(servicio_id=measured.service.id, timestamp=at, intervalo_at=at,
            calidad='confirmada', estado_observado='running', cpu_usage_percent=1, ram_usage_mb=128))
    await db.commit()
    rows = await obtener_historial(db, measured.service.id, 500, resolucion='hora')
    assert len(rows) == 2


async def test_bounded_buckets_keep_latest_real_row_ties_gaps_and_clipped_edges(db, measured):
    start = measured.now.replace(hour=3, minute=0, second=0) - timedelta(days=1)
    samples=[]
    # Legacy rows may share a timestamp; larger id deterministically wins.
    for minutes,cpu in [(5,1),(20,2),(20,3),(40,4),(190,5),(230,6),(245,7)]:
        row=MetricaSnapshot(servicio_id=measured.service.id,timestamp=start+timedelta(minutes=minutes),
            intervalo_at=None,calidad='confirmada',estado_observado='running',cpu_usage_percent=cpu)
        db.add(row); await db.flush(); samples.append(row)
    await db.commit()
    bounded=await obtener_historial(db,measured.service.id,500,desde=start+timedelta(minutes=10),
        hasta=start+timedelta(minutes=240),resolucion='hora')
    # First/last hour clipped, two entirely missing buckets are not zeroes.
    assert [r.id for r in bounded] == [samples[3].id,samples[5].id]
    tight=await obtener_historial(db,measured.service.id,500,desde=start+timedelta(minutes=10),
        hasta=start+timedelta(minutes=25),resolucion='hora')
    assert [r.id for r in tight] == [samples[2].id]
