import logging
from datetime import timedelta

from sqlalchemy import select

from app.models.notificacion import Notificacion
from app.utils.clock import clock
from app.utils.secretos import configured_keyring
from tests import factories
from tests.test_auth_contrato_009 import auth_configuration
import pytest

pytestmark = pytest.mark.usefixtures('auth_configuration')


async def test_welcome_is_transactional_encrypted_and_retries_without_logging_password(db, caplog):
    from app.services.notificacion_service import encolar_bienvenida, procesar_uno
    user = await factories.crear_usuario(db, 'outbox')
    user.debe_cambiar_password = True
    notification = await encolar_bienvenida(db, user, 'Provisoria123!')
    await db.commit()
    assert notification.catedra_id is None
    assert 'Provisoria123!' not in str(notification.payload)
    assert 'Provisoria123!' not in notification.secreto_temporal_encrypted
    assert configured_keyring().decrypt(notification.secreto_temporal_encrypted, context=f'welcome:{notification.id}') == 'Provisoria123!'
    calls = []
    def fail(*args, **kwargs):
        calls.append(kwargs['message_id'])
        raise RuntimeError('SMTP error with untrusted server contents Provisoria123!')
    with caplog.at_level(logging.INFO):
        await procesar_uno(db, sender=fail)
    await db.refresh(notification)
    assert notification.estado == 'fallida' and notification.intentos == 1
    assert 'Provisoria123!' not in caplog.text
    notification.proximo_intento_at = clock.now() - timedelta(seconds=1)
    await db.commit()
    def succeed(*args, **kwargs):
        calls.append(kwargs['message_id'])
    await procesar_uno(db, sender=succeed)
    await db.refresh(notification)
    assert notification.estado == 'enviada' and notification.secreto_temporal_encrypted is None
    assert calls[0] == calls[1]


async def test_password_change_or_expiry_cancels_without_sending_and_rollback_does_not_queue(db):
    from app.services.notificacion_service import encolar_bienvenida, procesar_uno
    user = await factories.crear_usuario(db, 'stale_welcome')
    user.debe_cambiar_password = True
    await db.commit()
    await encolar_bienvenida(db, user, 'Provisoria123!')
    await db.rollback()
    assert (await db.scalars(select(Notificacion))).all() == []
    await db.refresh(user)
    value = await encolar_bienvenida(db, user, 'Provisoria123!')
    await db.commit()
    user.auth_version += 1
    await db.commit()
    def forbidden(*args, **kwargs):
        raise AssertionError('No enviar credenciales obsoletas')
    await procesar_uno(db, sender=forbidden)
    await db.refresh(value)
    assert value.estado == 'cancelada' and value.secreto_temporal_encrypted is None


def test_unconfigured_smtp_does_not_log_body_or_report_delivery(monkeypatch, caplog):
    from app.config import get_settings
    from app.services.email_service import despachar_email
    monkeypatch.setattr(get_settings(), 'smtp_host', '')
    # Se invoca la implementación real, no el doble autouse.
    from tests.conftest import REAL_EMAIL_SENDER
    with pytest.raises(RuntimeError), caplog.at_level(logging.INFO):
        REAL_EMAIL_SENDER(['fixture@test.local'], 'Bienvenida', 'secret-not-for-logs', '<p>secret-not-for-logs</p>')
    assert 'secret-not-for-logs' not in caplog.text
