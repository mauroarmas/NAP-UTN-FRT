from copy import deepcopy
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, func

from app.models.evento_seguridad import EventoSeguridad
from app.models.pedido import Pedido, EstadoPedido
from app.models.servicio import Servicio, EstadoServicio
from app.models.vigencia import VigenciaAutorizada
from app.services.pedido_service import transicionar
from app.services.vigencia_service import resolver_fechas
from app.utils.clock import clock
from app.utils.secretos import configured_keyring
from tests.test_evidencias_009 import evidence_definition, prepared_instance_document


@pytest.fixture
async def prepared_access(db, prepared_instance_document, admin, auth_catedra):
    document = deepcopy(prepared_instance_document)
    document['entorno'] = 'real'  # Documento sintético de un ensayo aislado; no se envía a un portal operativo.
    service = await db.get(Servicio, document['resultado']['servicio_id'])
    await transicionar(db, service.pedido_id, EstadoPedido.EN_DESPLIEGUE, usuario=admin, motivo='Preparación simulada en fixture')
    service.estado = EstadoServicio.RUNNING
    service.disponibilidad_aplicacion = 'no_verificada'
    service.modelo_servicio = 'paas'
    service.verificado_at = clock.now() - timedelta(seconds=30)
    service.acceso_metadata = {'endpoint': document['resultado']['endpoint'], 'host': 'base.example.edu',
        'port': 5432, 'database': 'curso', 'username': 'nap_curso', 'metodo': 'postgresql',
        'local_health': True, 'preparacion_id': document['resultado']['preparacion_id']}
    service.credenciales_encrypted = configured_keyring().encrypt({'database_password': 'private-instance-test-only'}, context=f'servicio:{service.id}:secretos')
    today = clock.now().date()
    dates = resolver_fechas(today - timedelta(days=1), today + timedelta(days=30), 'America/Argentina/Tucuman')
    db.add(VigenciaAutorizada(pedido_id=service.pedido_id, servicio_id=service.id, revision_decision=1,
        modalidad='personalizado', desde_local=dates.desde, hasta_local=dates.hasta, zona_horaria=dates.zona_horaria,
        inicio_at=dates.inicio_at, fin_exclusivo_at=dates.fin_exclusivo_at))
    await db.commit()
    return service.id, document


async def test_confirmed_local_preparation_only_allows_admin_validation_reveal(client, db, prepared_access, auth_admin, auth_catedra, caplog):
    service_id, document = prepared_access
    metadata = await client.get(f'/servicios/{service_id}/acceso', headers=auth_catedra)
    assert metadata.status_code == 200
    assert metadata.json()['disponibilidad'] == 'no_verificada'
    assert not metadata.json()['puede_revelar_credenciales'] and metadata.headers['cache-control'] == 'no-store'
    denied = await client.post(f'/servicios/{service_id}/acceso/revelar', json={}, headers=auth_catedra)
    assert denied.status_code == 409
    revealed = await client.post(f'/servicios/{service_id}/acceso/revelar', json={}, headers=auth_admin)
    assert revealed.status_code == 200, revealed.text
    assert revealed.json()['estado_entrega'] == 'solo_validacion'
    assert revealed.json()['credenciales']['password'] == 'private-instance-test-only'
    assert revealed.headers['cache-control'] == 'no-store'
    assert 'private-instance-test-only' not in caplog.text
    request = await db.get(Pedido, (await db.get(Servicio, service_id)).pedido_id)
    assert request.estado == EstadoPedido.EN_DESPLIEGUE
    audit = list((await db.scalars(select(EventoSeguridad).where(EventoSeguridad.accion == 'revelar_acceso_servicio'))).all())
    assert len(audit) == 1 and 'private-instance-test-only' not in repr([row.motivo for row in audit])


async def test_instance_proof_must_be_imported_and_matching_before_delivery(client, db, prepared_access, auth_admin, auth_catedra):
    service_id, document = prepared_access
    imported = await client.post('/evidencias', json=document, headers=auth_admin | {'Idempotency-Key': 'access-proof'})
    assert imported.status_code == 201, imported.text
    body = {'evidencia_ref': imported.json()['evidencia_ref'], 'endpoint': document['resultado']['endpoint'], 'observado_at': document['observado_at']}
    url = f'/servicios/{service_id}/verificar-acceso'
    bad = await client.post(url, json={**body, 'evidencia_ref': str(uuid4())}, headers=auth_admin | {'Idempotency-Key': 'missing-proof'})
    assert bad.status_code == 404
    bad = await client.post(url, json={**body, 'endpoint': 'postgresql://other.invalid:5432/curso'}, headers=auth_admin | {'Idempotency-Key': 'wrong-endpoint'})
    assert bad.status_code == 409
    assert (await client.post(url, json=body, headers=auth_catedra | {'Idempotency-Key': 'teacher-verification'})).status_code == 403
    first = await client.post(url, json=body, headers=auth_admin | {'Idempotency-Key': 'verify-access'})
    assert first.status_code == 200, first.text
    repeated = await client.post(url, json=body, headers=auth_admin | {'Idempotency-Key': 'verify-access'})
    assert repeated.status_code == 200 and repeated.headers['idempotency-replayed'] == 'true'
    service = await db.get(Servicio, service_id, populate_existing=True)
    assert service.disponibilidad_aplicacion == 'utilizable' and service.evidencia_acceso_id == UUID(body['evidencia_ref'])
    assert (await db.get(Pedido, service.pedido_id, populate_existing=True)).estado == EstadoPedido.ACTIVO
    reveal = await client.post(f'/servicios/{service_id}/acceso/revelar', json={}, headers=auth_catedra)
    assert reveal.status_code == 200 and reveal.json()['estado_entrega'] == 'entregado'
    from app.models.notificacion import Notificacion
    notices = list((await db.scalars(select(Notificacion).where(Notificacion.servicio_id == service_id))).all())
    assert len([entry for entry in notices if entry.canal == 'portal']) == 1
    assert 'private-instance-test-only' not in repr([entry.payload for entry in notices])
    # Otra clave HTTP no duplica la entrega ya registrada para esa preparación.
    other = await client.post(url, json=body, headers=auth_admin | {'Idempotency-Key': 'verify-access-other-key'})
    assert other.status_code == 200
    assert await db.scalar(select(func.count()).select_from(Notificacion).where(Notificacion.servicio_id == service_id)) == len(notices)
    from app.services.notificacion_service import procesar_uno
    sent = []
    assert any(entry.canal == 'email' for entry in notices)
    assert await procesar_uno(db, sender=lambda *args, **kwargs: sent.append(args))
    assert len(sent) == 1 and 'private-instance-test-only' not in repr(sent)


async def test_foreign_owner_is_denied_before_any_decryption(client, db, prepared_access, monkeypatch):
    from tests.factories import crear_usuario
    from tests.auth_helpers import headers_para
    import app.services.service_access_service as access
    def forbidden_decryption(*args, **kwargs):
        raise AssertionError('No se debe descifrar información de otra cátedra')
    monkeypatch.setattr(access, 'configured_keyring', forbidden_decryption)
    foreign = await crear_usuario(db, 'foreign-access')
    response = await client.post(f'/servicios/{prepared_access[0]}/acceso/revelar', json={}, headers=await headers_para(db, foreign))
    assert response.status_code == 403


async def test_bookstack_reveal_never_exposes_database_password_or_app_key(client, db, prepared_access, auth_admin):
    from app.models.definicion_servicio import DefinicionServicio
    service = await db.get(Servicio, prepared_access[0])
    definition = await db.get(DefinicionServicio, service.definicion_version_id)
    definition.producto, definition.modelo_servicio = 'bookstack', 'saas'
    service.modelo_servicio = 'saas'
    service.acceso_metadata = {**service.acceso_metadata, 'metodo': 'https', 'endpoint': 'https://libro.example.edu',
        'host': 'libro.example.edu', 'port': 443, 'username': 'docente@example.edu'}
    service.credenciales_encrypted = configured_keyring().encrypt({'teacher_password': 'teacher-test-private-value',
        'database_password': 'internal-db-test-private-value', 'app_key': 'internal-app-key-test-private-value'},
        context=f'servicio:{service.id}:secretos')
    await db.commit()
    metadata = await client.get(f'/servicios/{service.id}/acceso', headers=auth_admin)
    reveal = await client.post(f'/servicios/{service.id}/acceso/revelar', json={}, headers=auth_admin)
    assert reveal.status_code == 200, reveal.text
    assert reveal.json()['credenciales']['password'] == 'teacher-test-private-value'
    assert 'internal-db-test-private-value' not in metadata.text + reveal.text
    assert 'internal-app-key-test-private-value' not in metadata.text + reveal.text
    assert 'teacher-test-private-value' not in metadata.text


async def test_stopped_instance_does_not_advertise_or_reveal_usable_access(client, db, prepared_access, auth_admin):
    service = await db.get(Servicio, prepared_access[0]); service.estado = EstadoServicio.STOPPED
    await db.commit()
    metadata = await client.get(f'/servicios/{service.id}/acceso', headers=auth_admin)
    assert not metadata.json()['puede_revelar_credenciales']
    reveal = await client.post(f'/servicios/{service.id}/acceso/revelar', json={}, headers=auth_admin)
    assert reveal.status_code == 409


async def test_bookstack_acceptance_requires_reader_revocation_and_private_files(client, db, prepared_access, auth_admin):
    from app.models.definicion_servicio import DefinicionServicio
    service_id, original = prepared_access
    service = await db.get(Servicio, service_id)
    definition = await db.get(DefinicionServicio, service.definicion_version_id)
    definition.producto, definition.modelo_servicio = 'bookstack', 'saas'
    service.modelo_servicio = 'saas'
    service.acceso_metadata = {**service.acceso_metadata, 'metodo': 'https', 'host': 'libro.example.edu',
        'endpoint': 'https://libro.example.edu', 'port': 443, 'username': 'docente@example.edu'}
    service.credenciales_encrypted = configured_keyring().encrypt({'teacher_password': 'teacher-private-test-value',
        'database_password': 'database-private-test-value', 'app_key': 'app-key-private-test-value'},
        context=f'servicio:{service_id}:secretos')
    await db.commit()
    document = deepcopy(original)
    document['resultado'].update(endpoint='https://libro.example.edu',
        pruebas=['publicacion_docente', 'lectura_individual', 'persistencia'])
    incomplete = await client.post('/evidencias', json=document, headers=auth_admin | {'Idempotency-Key': 'book-incomplete'})
    assert incomplete.status_code == 422
    document['resultado']['pruebas'] += ['permisos_lectores', 'revocacion_individual', 'archivos_privados']
    imported = await client.post('/evidencias', json=document, headers=auth_admin | {'Idempotency-Key': 'book-complete'})
    assert imported.status_code == 201, imported.text
    verified = await client.post(f'/servicios/{service_id}/verificar-acceso', json={
        'evidencia_ref': imported.json()['evidencia_ref'], 'endpoint': document['resultado']['endpoint'],
        'observado_at': document['observado_at']}, headers=auth_admin | {'Idempotency-Key': 'book-verify'})
    assert verified.status_code == 200, verified.text


@pytest.mark.parametrize('kind', ['simulation', 'tampered', 'wrong_type', 'old_preparation'])
async def test_unusable_evidence_never_delivers_access(client, db, prepared_access, auth_admin, admin, monkeypatch, kind):
    from app.config import get_settings
    from sqlalchemy import text
    service_id, document = prepared_access
    if kind == 'simulation':
        monkeypatch.setattr(get_settings(), 'app_env', 'test')
        from tests.auth_helpers import headers_para
        auth_admin = await headers_para(db, admin)
        document['entorno'] = 'simulado'
    imported = await client.post('/evidencias', json=document, headers=auth_admin | {'Idempotency-Key': 'proof-' + kind})
    assert imported.status_code == 201, imported.text
    ref = imported.json()['evidencia_ref']
    if kind == 'tampered':
        await db.execute(text("UPDATE evidencias SET documento_canonico = '{}' WHERE id = :id"), {'id': ref.replace('-', '')})
        await db.commit()
    if kind == 'wrong_type':
        await db.execute(text("UPDATE evidencias SET tipo = 'validacion_definicion' WHERE id = :id"), {'id': ref.replace('-', '')})
        await db.commit()
    if kind == 'old_preparation':
        from app.models.operacion_infraestructura import OperacionInfraestructura
        old = await db.get(OperacionInfraestructura, UUID(document['resultado']['preparacion_id']))
        db.add(OperacionInfraestructura(tipo='reparar', servicio_id=service_id, pedido_id=old.pedido_id,
            identidad_infraestructura_id=old.identidad_infraestructura_id, estado='confirmada',
            actor_id_normalizado='test', idempotency_key='new-preparation', request_hash='f' * 64,
            confirmada_at=clock.now(), creado_at=clock.now()))
        await db.commit()
    response = await client.post(f'/servicios/{service_id}/verificar-acceso',
        json={'evidencia_ref': ref, 'endpoint': document['resultado']['endpoint'], 'observado_at': document['observado_at']},
        headers=auth_admin | {'Idempotency-Key': 'verify-' + kind})
    assert response.status_code in {409, 422}, response.text
    service = await db.get(Servicio, service_id, populate_existing=True)
    assert service.disponibilidad_aplicacion == 'no_verificada' and service.evidencia_acceso_id is None
