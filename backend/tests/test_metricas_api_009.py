from datetime import timedelta
from urllib.parse import urlencode

from sqlalchemy import insert

from app.models.metrica import MetricaSnapshot
from app.models.servicio import EstadoServicio
from app.utils.clock import clock
from tests import factories
from tests.capacity_helpers import perfil_capacidad  # noqa: F401
from tests.test_metricas_intervalos_009 import measured  # noqa: F401


async def test_service_model_filter_keeps_current_category_scope(client, db, measured, auth_catedra, auth_admin):
    measured.service.modelo_servicio = 'iaas'
    owner = await factories.crear_usuario(db, 'titular-filtro-ajeno')
    category = await factories.crear_catedra(db, nombre='Filtro ajeno', titular_id=owner.id)
    other = await factories.crear_servicio(db, category.id, measured.service.template_id, proxmox_vmid=None)
    other.modelo_servicio = 'paas'
    await db.commit()
    own = await client.get('/servicios/?modelo_servicio=iaas', headers=auth_catedra)
    assert own.status_code == 200 and [r['id'] for r in own.json()] == [measured.service.id]
    assert (await client.get('/servicios/?modelo_servicio=paas', headers=auth_catedra)).json() == []
    admin = await client.get('/servicios/?modelo_servicio=paas', headers=auth_admin)
    assert admin.status_code == 200 and [r['id'] for r in admin.json()] == [other.id]
    assert (await client.get('/servicios/?modelo_servicio=qemu', headers=auth_admin)).status_code == 422


async def test_range_resolution_is_bounded_and_keeps_real_observations(client, db, measured, auth_admin):
    start = measured.now - timedelta(days=2)
    rows = [dict(servicio_id=measured.service.id, timestamp=start + timedelta(minutes=i),
        intervalo_at=(start + timedelta(minutes=i)).replace(second=0), calidad='confirmada', estado_observado='running',
        cpu_usage_percent=10, ram_usage_mb=128, disk_usage_gb=1,
        net_in_bytes=2**54+1, net_out_bytes=2**54+3, duracion_observada_s=0) for i in range(1000)]
    await db.execute(insert(MetricaSnapshot), rows)
    await db.commit()
    query = urlencode({'desde': start.isoformat(), 'hasta': measured.now.isoformat(), 'resolucion': 'hora', 'limit': 500})
    response = await client.get(f'/metricas/{measured.service.id}/historial?{query}', headers=auth_admin)
    assert response.status_code == 200
    data = response.json()
    assert 1 < len(data) < 30
    assert all(row['calidad'] == 'confirmada' and row['net_in_bytes'] == 2**54+1 for row in data)
    assert data == sorted(data, key=lambda row: row['timestamp'])
    assert (await client.get(f'/metricas/{measured.service.id}/historial?limit=501', headers=auth_admin)).status_code == 422
    assert (await client.get(f'/metricas/{measured.service.id}/historial?desde=2026-01-01T00:00:00', headers=auth_admin)).status_code == 422


async def test_summary_marks_assignment_fallback_instead_of_fabricating_observed_limits(client, measured, auth_admin):
    response = await client.get('/metricas/resumen', headers=auth_admin)
    assert response.status_code == 200
    row = response.json()[0]
    assert row['ultimo_snapshot'] is None
    assert row['limites_fuente']['ram'] == 'asignacion_estimada'
    assert row['estado_observado'] is None and row['observado_at'] is None


async def test_mail_failure_state_is_admin_only_and_contains_no_payload_or_encrypted_values(
    client, db, measured, auth_admin, auth_catedra,
):
    from app.services.notificacion_service import encolar_aviso_servicio, procesar_uno
    await encolar_aviso_servicio(db, measured.service, evento='prueba-correo-fallido', tipo='prueba',
        asunto='Aviso', texto='Consultá el portal')
    await db.commit()
    def failure(*args, **kwargs): raise RuntimeError('smtp-private-value')
    await procesar_uno(db, sender=failure)
    response = await client.get('/alertas/correo?estado=fallida', headers=auth_admin)
    assert response.status_code == 200 and response.json()
    row = response.json()[0]
    assert row['ultimo_error'] == 'entrega_no_confirmada'
    assert 'payload' not in row and 'destinatario_email_cifrado' not in row
    assert 'smtp-private-value' not in response.text
    assert (await client.get('/alertas/correo', headers=auth_catedra)).status_code == 403


async def test_alerts_filter_by_current_category_and_portal_notice_scope(client, db, measured, auth_catedra, auth_admin):
    from app.models.incidente import Incidente
    from app.services.notificacion_service import encolar_aviso_servicio
    other_owner = await factories.crear_usuario(db, 'titular-alerta-ajena')
    other_cat = await factories.crear_catedra(db, nombre='Otra cátedra', titular_id=other_owner.id)
    other = await factories.crear_servicio(db, other_cat.id, measured.service.template_id, proxmox_vmid=None)
    for service in [measured.service, other]:
        db.add(Incidente(servicio_id=service.id, tipo='caida', abierto_at=clock.now(),
            ultima_observacion_at=clock.now(), regla_version='fixture', evidencia={'muestras': []}))
        await encolar_aviso_servicio(db, service, evento=f'alerta-fixture:{service.id}', tipo='incidente_apertura',
            asunto='Aviso', texto='Consultá el portal')
    await db.commit()
    teacher = await client.get('/alertas', headers=auth_catedra)
    assert teacher.status_code == 200
    assert {row['servicio_id'] for row in teacher.json()} == {measured.service.id}
    notices = await client.get('/alertas/avisos', headers=auth_catedra)
    assert notices.status_code == 200
    assert {row['servicio_id'] for row in notices.json()} == {measured.service.id}
    administrator = await client.get('/alertas', headers=auth_admin)
    assert administrator.status_code == 200 and len(administrator.json()) == 2
