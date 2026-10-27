from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select

from app.models.restauracion import Restauracion
from app.models.operacion_infraestructura import OperacionInfraestructura
from app.services import restauracion_service as restore, preflight_service
from app.utils.clock import clock
from tests.capacity_helpers import perfil_capacidad, materializado  # noqa:F401


@pytest.fixture
def prepared_checks(monkeypatch):
    # Estos tests aíslan la comparación del corte; config/ofertas tienen suites propias.
    monkeypatch.setattr(preflight_service, 'validar_configuracion', lambda _: {'apto': True, 'hallazgos': []})
    async def valid(_): return {'apto': True, 'hallazgos': []}
    monkeypatch.setattr(preflight_service, 'inspeccionar_datos', valid)
    monkeypatch.setattr(preflight_service, 'inspeccionar_ofertas', valid)


def proof(report):
    now = clock.now()
    return {'restauracion_id': report['restauracion_id'], 'referencia_corte': report['referencia'],
        'referencia_ensayo': 'ensayo-separado-009', 'entorno': 'simulado',
        'estado_sha256': report['estado_sha256'], 'conjunto_sha256': 'a'*64,
        'inicio_at': (now - timedelta(seconds=2)).isoformat(), 'fin_at': (now - timedelta(seconds=1)).isoformat(),
        'portal_keyring': True, 'postgresql_dato': True,
        'bookstack_libro_imagen_adjunto_cuentas_permisos': True,
        'inventario_operaciones_capacidad_acceso_reconciliados': True}


@pytest.mark.parametrize('value', [False, 1, 'true', None])
def test_attestation_requires_actual_boolean_confirmations(value):
    from app.schemas.restauracion import PruebaRestauracion
    body = proof({'restauracion_id':str(uuid4()), 'referencia':'corte', 'estado_sha256':'b'*64})
    body['portal_keyring'] = value
    with pytest.raises(ValidationError): PruebaRestauracion.model_validate(body)


async def prepare(db):
    result = await restore.preparar_restauracion(db, operador='operador', referencia='corte-ensayo')
    # Tiempo de comienzo anterior a la atestación fixture, sin esperas artificiales.
    row = await db.get(Restauracion, UUID(result['restauracion_id']))
    row.preparada_at = clock.now() - timedelta(seconds=10)
    await db.commit()
    return result


async def test_exact_cut_requires_separate_proof_and_enables_once(db, admin, proxmox, perfil_capacidad,
    catedra, usuario_catedra, template, prepared_checks, client, auth_admin):
    await materializado(db, proxmox, catedra, usuario_catedra, template)
    await prepare(db)
    assert (await client.get('/auth/me', headers=auth_admin)).status_code == 503
    report = await restore.evaluar_habilitacion(db, 'corte-ensayo', pve=proxmox)
    assert report['apto'], report
    bad = proof(report) | {'referencia_ensayo': 'corte-ensayo'}
    with pytest.raises(ValidationError): await restore.habilitar_restauracion(db, operador='operador', prueba=bad, pve=proxmox)
    result = await restore.habilitar_restauracion(db, operador='operador', prueba=proof(report), pve=proxmox)
    await db.commit()
    assert result['estado'] == 'habilitada'
    assert (await client.get('/auth/me', headers=auth_admin)).status_code == 401
    response = await client.post('/auth/login', data={'username': admin.username, 'password': 'secreto123'})
    assert response.status_code == 200 and response.json()['estado'] == 'operativo'
    for component in ['api', 'worker', 'outbox']: await restore.exigir_habilitacion(db, componente=component)
    version = admin.auth_version
    with pytest.raises(HTTPException) as exc:
        await restore.preparar_restauracion(db, operador='operador', referencia='corte-ensayo')
    assert exc.value.detail['codigo'] == 'referencia_restauracion_utilizada'
    await db.refresh(admin); assert admin.auth_version == version
    assert proxmox.creados == proxmox.iniciados == proxmox.eliminados == []


async def test_changed_inventory_or_account_invalidates_reviewed_state(db, admin, proxmox, perfil_capacidad,
    catedra, usuario_catedra, template, prepared_checks):
    _, ledger = await materializado(db, proxmox, catedra, usuario_catedra, template)
    await prepare(db)
    report = await restore.evaluar_habilitacion(db, 'corte-ensayo', pve=proxmox)
    admin.auth_version += 1; await db.commit()
    with pytest.raises(HTTPException) as exc:
        await restore.habilitar_restauracion(db, operador='operador', prueba=proof(report), pve=proxmox)
    assert exc.value.detail['codigo'] == 'reconciliacion_restauracion_pendiente'
    proxmox.recursos[0]['status'] = 'running'
    changed = await restore.evaluar_habilitacion(db, 'corte-ensayo', pve=proxmox)
    assert not changed['apto'] and 'asignacion_y_ledger_no_reconciliados' in changed['pendientes']
    await db.refresh(ledger); assert ledger.vcpus_retenidos == 0 and ledger.disk_bytes_retenidos > 0


async def test_orphan_marker_and_lost_ownership_never_adopt_or_release(db, proxmox, perfil_capacidad,
    catedra, usuario_catedra, template, prepared_checks):
    _, ledger = await materializado(db, proxmox, catedra, usuario_catedra, template)
    await prepare(db)
    import json
    config = proxmox.configuraciones[('pve1', 100)]
    mark = json.loads(config['description']); mark['nap']['resource_uuid'] = str(uuid4())
    config['description'] = json.dumps(mark)
    report = await restore.evaluar_habilitacion(db, 'corte-ensayo', pve=proxmox)
    assert not report['apto'] and 'recurso_nap_fuera_del_corte' in report['pendientes']
    await db.refresh(ledger); assert ledger.liberado_at is None and ledger.disk_bytes_retenidos > 0
    with pytest.raises(HTTPException): await restore.exigir_habilitacion(db, componente='worker')
    assert proxmox.creados == proxmox.eliminados == []


async def test_open_operation_fenced_and_capacity_held_until_resolution(db, admin, proxmox, perfil_capacidad,
    catedra, usuario_catedra, template, prepared_checks):
    service, ledger = await materializado(db, proxmox, catedra, usuario_catedra, template)
    operation = OperacionInfraestructura(tipo='iniciar', servicio_id=service.id,
        identidad_infraestructura_id=service.identidad_infraestructura_id,
        actor_usuario_id=admin.id, actor_tipo='usuario', actor_id_normalizado=str(admin.id),
        idempotency_key='restore-open', request_hash='b'*64, estado='en_curso', fase='poll',
        upid='UPID:fixture:restored', lease_owner=uuid4(), lease_generation=3)
    db.add(operation); await db.commit()
    disk = ledger.disk_bytes_retenidos
    await prepare(db); await db.refresh(operation); await db.refresh(ledger)
    assert operation.estado == 'incierta' and operation.fase == 'restauracion_pendiente'
    assert operation.upid == 'UPID:fixture:restored' and operation.lease_generation == 4 and operation.lease_owner is None
    assert operation.contexto_seguro['corte_restaurado']['fase_anterior'] == 'poll'
    assert ledger.estado == 'incierto' and ledger.disk_bytes_retenidos == disk and ledger.liberado_at is None
    report = await restore.evaluar_habilitacion(db, 'corte-ensayo', pve=proxmox)
    assert not report['apto'] and 'operaciones_abiertas_del_corte' in report['pendientes']


async def test_simulated_attestation_rejected_in_production_before_probe(db, monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), 'app_env', 'production')
    body = proof({'restauracion_id': str(uuid4()), 'referencia': 'corte', 'estado_sha256': 'b'*64})
    with pytest.raises(HTTPException) as exc:
        await restore.habilitar_restauracion(db, operador='operador', prueba=body)
    assert exc.value.detail['codigo'] == 'ensayo_simulado_no_operativo'


@pytest.mark.parametrize('change', ['privileged', 'bind_mount', 'power_changed'])
async def test_changed_container_security_or_power_cannot_reenable_cut(db, proxmox, perfil_capacidad,
    catedra, usuario_catedra, template, prepared_checks, change):
    await materializado(db, proxmox, catedra, usuario_catedra, template)
    await prepare(db)
    config = proxmox.configuraciones[('pve1', 100)]
    if change == 'privileged': config['unprivileged'] = 0
    elif change == 'bind_mount': config['mp0'] = '/srv/origen,mp=/datos'
    else: proxmox.recursos[0]['status'] = 'running'
    result = await restore.evaluar_habilitacion(db, 'corte-ensayo', pve=proxmox)
    assert not result['apto'] and 'asignacion_y_ledger_no_reconciliados' in result['pendientes']
