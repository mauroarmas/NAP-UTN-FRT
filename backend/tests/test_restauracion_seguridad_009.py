"""Restaurar un corte no puede resucitar credenciales efímeras consumidas."""
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from fastapi import HTTPException

from app.models.autenticacion import SesionAutenticacion, DesafioAutenticacion, CodigoRecuperacion
from app.models.notificacion import Notificacion
from app.utils.clock import clock
from app.utils.secretos import configured_keyring, SecretError


async def restored_rows(db,user):
    keyring=configured_keyring()
    user.totp_habilitado=True
    user.totp_secret_encrypted=keyring.encrypt('JBSWY3DPEHPK3PXP',context=f'totp:{user.id}')
    user.totp_last_step=10
    session=SesionAutenticacion(usuario_id=user.id,proposito='operativo',auth_version=user.auth_version,
        expira_at=clock.now()+timedelta(hours=1))
    db.add(session);await db.flush()
    challenge=DesafioAutenticacion(id=uuid4(),usuario_id=user.id,sesion_id=session.id,tipo='enrollment',
        expira_at=clock.now()+timedelta(minutes=5))
    challenge.secreto_pendiente_cifrado=keyring.encrypt('pending',context=f'totp-pending:{challenge.id}')
    code=CodigoRecuperacion(usuario_id=user.id,generacion=user.recovery_generation,codigo_hash='a'*64)
    db.add_all([challenge,code])
    from app.services.notificacion_service import encolar_bienvenida
    user.debe_cambiar_password=True
    notice=await encolar_bienvenida(db,user,'temporary-fixture-password')
    await db.commit()
    return session,challenge,code,notice


async def test_restore_revokes_old_sessions_challenges_codes_and_welcome_but_preserves_mfa(db,admin):
    from app.services.restauracion_service import preparar_restauracion, exigir_habilitacion
    session,challenge,code,notice=await restored_rows(db,admin)
    original=admin.totp_secret_encrypted;password=admin.password_hash;version=admin.auth_version
    result=await preparar_restauracion(db,operador='operador-prueba',referencia='corte-009-prueba')
    await db.commit()
    for row in [admin,session,challenge,code,notice]: await db.refresh(row)
    assert admin.auth_version==version+1 and admin.password_hash==password
    assert admin.totp_habilitado and admin.totp_secret_encrypted==original
    assert configured_keyring().decrypt(original,context=f'totp:{admin.id}')=='JBSWY3DPEHPK3PXP'
    assert session.revoked_at is not None and challenge.revocado_at is not None
    assert challenge.secreto_pendiente_cifrado is None and code.invalidado_at is not None
    assert notice.estado=='cancelada' and notice.secreto_temporal_encrypted is None
    for component in ['api','worker','outbox']:
        with pytest.raises(HTTPException) as exc: await exigir_habilitacion(db,componente=component)
        assert exc.value.status_code==503 and exc.value.detail['codigo']=='restauracion_pendiente'
    from app.services.auth_service import usuario_bloqueado
    with pytest.raises(HTTPException) as locked_user: await usuario_bloqueado(db, admin)
    assert locked_user.value.detail['codigo'] == 'restauracion_pendiente'
    again=await preparar_restauracion(db,operador='operador-prueba',referencia='corte-009-prueba')
    assert again['restauracion_id']==result['restauracion_id']
    await db.refresh(admin);assert admin.auth_version==version+1


async def test_missing_decryption_key_aborts_before_any_credential_is_changed(db,admin,monkeypatch):
    from app.services.restauracion_service import preparar_restauracion
    from app.config import get_settings
    session,challenge,code,notice=await restored_rows(db,admin)
    original_version=admin.auth_version
    monkeypatch.setattr(get_settings(),'secret_keyring',{})
    with pytest.raises(SecretError):
        await preparar_restauracion(db,operador='operador-prueba',referencia='corte-clave-ausente')
    await db.refresh(admin);await db.refresh(session);await db.refresh(notice)
    assert admin.auth_version==original_version and session.revoked_at is None
    assert notice.secreto_temporal_encrypted is not None


async def test_restore_rejects_empty_operator_or_reference_without_mutation(db,admin):
    from app.services.restauracion_service import preparar_restauracion
    with pytest.raises(ValueError): await preparar_restauracion(db,operador='',referencia='')
    assert (await db.scalars(select(Notificacion))).all()==[]


async def test_all_old_email_jobs_cancelled_and_leases_fenced(db, admin):
    from app.services.restauracion_service import preparar_restauracion
    from app.models.restauracion import AccesoInicialRestaurado
    session, challenge, code, notice = await restored_rows(db, admin)
    notice.estado = 'enviando'; notice.lease_owner = 'old-worker'; notice.generation = 4
    other = Notificacion(evento_clave='old-alert', destinatario_usuario_id=admin.id,
        destinatario_normalizado=f'usuario:{admin.id}', canal='email', payload={'tipo':'alerta'}, estado='fallida')
    db.add(other); await db.commit()
    await preparar_restauracion(db, operador='operador', referencia='corte-alertas')
    await db.commit(); await db.refresh(notice); await db.refresh(other)
    assert notice.lease_owner is None and notice.lease_hasta is None and notice.generation == 5
    assert other.estado == 'cancelada' and other.ultimo_error == 'corte_restaurado'
    assert await db.scalar(select(AccesoInicialRestaurado.id).where(AccesoInicialRestaurado.usuario_id == admin.id))


async def test_pending_restore_blocks_login_worker_smtp_and_scheduler_before_effects(db, admin, client, engine, monkeypatch):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.services.restauracion_service import preparar_restauracion
    from app.services import notificacion_service, scheduler, operacion_service
    from app.worker import procesar_una
    await preparar_restauracion(db, operador='operador', referencia='corte-bloqueo'); await db.commit()
    username = admin.username
    calls = []
    async def forbidden(*args, **kwargs): calls.append(True); raise AssertionError('No debe reclamar')
    monkeypatch.setattr(operacion_service, 'reclamar', forbidden)
    monkeypatch.setattr(notificacion_service, '_claim', forbidden)
    monkeypatch.setitem(scheduler.TRABAJOS, 'fixture-restauracion', (forbidden, 1))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    for action in [lambda: procesar_una(sessions), lambda: notificacion_service.procesar_uno(db),
                   lambda: scheduler.ejecutar('fixture-restauracion', db=db)]:
        with pytest.raises(HTTPException) as exc: await action()
        assert exc.value.detail['codigo'] == 'restauracion_pendiente'
        await db.rollback()
    response = await client.post('/auth/login', data={'username':username, 'password':'Some-password-123'})
    assert response.status_code == 503 and response.json()['detail']['codigo'] == 'restauracion_pendiente'
    assert calls == []


async def test_external_restore_reference_blocks_even_before_preparation(db, monkeypatch):
    from app.config import get_settings
    from app.services.restauracion_service import exigir_habilitacion
    monkeypatch.setattr(get_settings(), 'restauracion_referencia', 'copia-nueva-no-preparada')
    with pytest.raises(HTTPException) as exc: await exigir_habilitacion(db, componente='api')
    assert exc.value.status_code == 503


async def test_temporary_password_requires_authorized_reissue_preserving_factor(db, admin):
    from app.services.restauracion_service import preparar_restauracion, exigir_acceso_reemitido, reemitir_acceso_inicial
    from app.utils.security import verificar_password_async
    await restored_rows(db, admin)
    original_factor = admin.totp_secret_encrypted
    await preparar_restauracion(db, operador='operador', referencia='corte-acceso'); await db.commit()
    with pytest.raises(HTTPException) as exc: await exigir_acceso_reemitido(db, admin)
    assert exc.value.detail['codigo'] == 'acceso_inicial_requiere_reemision'
    from app.services.restauracion_service import validar_password_reemision
    with pytest.raises(HTTPException) as reused: await validar_password_reemision(db, admin, 'secreto123')
    assert reused.value.detail['codigo'] == 'password_restaurada_no_reutilizable'
    with pytest.raises(ValueError):
        await reemitir_acceso_inicial(db, admin.id, 'Nueva-clave-prueba-123', operador='', referencia='identidad')
    await reemitir_acceso_inicial(db, admin.id, 'Nueva-clave-prueba-123', operador='responsable', referencia='identidad-comprobada')
    await db.commit(); await exigir_acceso_reemitido(db, admin)
    assert await verificar_password_async('Nueva-clave-prueba-123', admin.password_hash)
    assert admin.debe_cambiar_password and admin.totp_habilitado and admin.totp_secret_encrypted == original_factor
    assert (await db.scalars(select(Notificacion).where(Notificacion.estado=='pendiente'))).all() == []


async def test_restore_reference_cannot_be_changed_while_pending(db, admin):
    from app.services.restauracion_service import preparar_restauracion
    first = await preparar_restauracion(db, operador='operador', referencia='corte-uno'); await db.commit()
    version = admin.auth_version
    with pytest.raises(HTTPException) as exc:
        await preparar_restauracion(db, operador='operador', referencia='corte-dos')
    assert exc.value.status_code == 409
    await db.refresh(admin); assert admin.auth_version == version
    assert first['estado'] == 'pendiente'
