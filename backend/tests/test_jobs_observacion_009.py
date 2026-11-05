from sqlalchemy import select

from app.models.job_lock import JobLock
from app.services import scheduler
from app.worker import registrar_trabajos


def test_observation_registry_has_one_cadence_for_each_job():
    registrar_trabajos()
    for name in ['recolectar_metricas','evaluar_alertas','aplicar_vencimientos','expirar_reservas']:
        assert scheduler.TRABAJOS[name][1] == 1
    assert scheduler.TRABAJOS['evaluar_inactividad'][1] == 60
    assert scheduler.TRABAJOS['agregar_y_purgar_metricas'][1] == 1440
    assert scheduler.CADENCIAS_SEGUNDOS['procesar_operaciones'] == 5
    assert 'capturar_metricas' not in scheduler.TRABAJOS


async def test_manual_batch_and_single_capture_respect_the_periodic_capture_lock(db, client, auth_admin, catedra, template):
    from tests import factories
    service = await factories.crear_servicio(db, catedra.id, template.id)
    lease = await scheduler.adquirir_job(db, 'recolectar_metricas')
    try:
        for path in ['/metricas/capturar', f'/metricas/capturar/{service.id}', '/admin/jobs/recolectar_metricas']:
            response = await client.post(path, headers=auth_admin)
            assert response.status_code == 409, response.text
        current = await db.scalar(select(JobLock).where(JobLock.nombre == 'recolectar_metricas'))
        assert current.owner_token == lease.owner
    finally:
        await scheduler.liberar_job(db, lease)


async def test_daily_job_trigger_is_institutional_and_survives_worker_restart(monkeypatch):
    registrar_trabajos()
    instance = scheduler.iniciar()
    try:
        job = instance.get_job('agregar_y_purgar_metricas')
        assert job.trigger.__class__.__name__ == 'CronTrigger'
        assert str(job.trigger.timezone) == 'America/Argentina/Tucuman'
        operations = instance.get_job('procesar_operaciones')
        assert operations.trigger.interval.total_seconds() == 5
    finally:
        scheduler.detener()
