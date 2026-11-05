"""Regresiones del contrato común, unidades y calendario institucional."""

from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError


@pytest.mark.parametrize('changes', [
    {'vcpus': 0}, {'ram_mb': -1}, {'disk_gb': 0}, {'vcpus': True},
    {'disk_gb': 1.5}, {'vmid': 999}, {'nonce': 'no-publicar'},
])
def test_resources_reject_invalid_values_and_unknown_fields(changes):
    from app.schemas.common import Recursos
    with pytest.raises(ValidationError):
        Recursos(**({'vcpus': 2, 'ram_mb': 1024, 'disk_gb': 16} | changes))


def test_large_disk_is_gib_and_ram_is_mib():
    from app.schemas.common import Recursos
    value = Recursos(vcpus=2, ram_mb=1024, disk_gb=16)
    assert value.disk_bytes == 16 * 1024**3
    assert value.ram_bytes == 1024 * 1024**2


def test_snapshots_cannot_include_credentials_or_overrides():
    from app.schemas.common import SnapshotDecision
    with pytest.raises(ValidationError):
        SnapshotDecision(asignacion={'vcpus': 1, 'ram_mb': 512, 'disk_gb': 8},
                         destino={'nodo': 'pve1', 'storage': 'local-lvm'},
                         credenciales={'password': 'NO-DEBE-PERSISTIR'})


def test_inclusive_local_end_becomes_next_day_exclusive_utc():
    from app.services.vigencia_service import resolver_fechas
    result = resolver_fechas(date(2027, 3, 1), date(2027, 6, 30), 'America/Argentina/Tucuman')
    assert result.inicio_at == datetime(2027, 3, 1, 3, tzinfo=timezone.utc)
    assert result.fin_exclusivo_at == datetime(2027, 7, 1, 3, tzinfo=timezone.utc)
    assert result.contiene(datetime(2027, 7, 1, 2, 59, 59, tzinfo=timezone.utc))
    assert not result.contiene(result.fin_exclusivo_at)


def test_invalid_date_range_or_zone_never_invents_a_period():
    from app.services.vigencia_service import resolver_fechas
    for since, until, zone in [
        (date(2027, 7, 1), date(2027, 6, 30), 'America/Argentina/Tucuman'),
        (date(2027, 3, 1), date(2027, 6, 30), 'zona-inexistente'),
    ]:
        with pytest.raises(ValueError):
            resolver_fechas(since, until, zone)


async def test_errors_have_structured_safe_detail(client, auth_admin):
    response = await client.get('/pedidos/999999', headers=auth_admin)
    assert response.status_code == 404
    assert isinstance(response.json()['detail'], dict)
    assert set(response.json()['detail']) >= {'codigo', 'mensaje', 'reintentable'}


async def test_no_approved_period_means_no_activation_even_for_legacy_service(db, catedra, template):
    from fastapi import HTTPException
    from tests.factories import crear_servicio
    from app.services.vigencia_service import exigir_cobertura
    service = await crear_servicio(db, catedra.id, template.id)
    with pytest.raises(HTTPException) as exc:
        await exigir_cobertura(db, service.id, datetime(2027, 3, 1, tzinfo=timezone.utc))
    assert exc.value.status_code == 409


async def test_approved_periods_preserve_the_gap_and_ignore_calendar_edits(db, catedra, template, admin):
    from fastapi import HTTPException
    from app.models.calendario import CalendarioLectivo
    from app.models.vigencia import VigenciaAutorizada
    from app.services.vigencia_service import exigir_cobertura, resolver_fechas
    from tests.factories import crear_pedido, crear_servicio
    service = await crear_servicio(db, catedra.id, template.id)
    calendar = CalendarioLectivo(anio=2027, revision=1)
    db.add(calendar)
    await db.flush()
    for since, until in [(date(2027, 3, 1), date(2027, 6, 30)), (date(2027, 8, 1), date(2027, 11, 30))]:
        pedido = await crear_pedido(db, catedra.id, admin.id, template.id)
        resolved = resolver_fechas(since, until, 'America/Argentina/Tucuman')
        db.add(VigenciaAutorizada(pedido_id=pedido.id, revision_decision=1, servicio_id=service.id,
            modalidad='personalizado', calendario_id=calendar.id, calendario_revision=1,
            desde_local=since, hasta_local=until, zona_horaria=resolved.zona_horaria,
            inicio_at=resolved.inicio_at, fin_exclusivo_at=resolved.fin_exclusivo_at))
    await db.commit()
    calendar.revision = 2
    await db.commit()
    with pytest.raises(HTTPException) as exc:
        await exigir_cobertura(db, service.id, datetime(2027, 7, 15, tzinfo=timezone.utc))
    assert exc.value.status_code == 409
    approved = await exigir_cobertura(db, service.id, datetime(2027, 8, 15, tzinfo=timezone.utc))
    assert approved.calendario_revision == 1
