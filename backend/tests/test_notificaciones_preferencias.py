"""Pruebas para preferencias de notificación por correo de los administradores."""

from datetime import timedelta
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catedra import Catedra
from app.models.usuario import Usuario, RolUsuario
from app.services import notificacion_service
from app.services.email_service import obtener_emails_administradores
from app.utils.clock import clock
from tests import factories
from tests.capacity_helpers import perfil_capacidad  # noqa: F401


def _vigencia():
    hoy = clock.now().astimezone(ZoneInfo("America/Argentina/Tucuman")).date()
    return {
        "tipo": "personalizado",
        "desde": hoy.isoformat(),
        "hasta": (hoy + timedelta(days=30)).isoformat(),
    }


@pytest.mark.asyncio
async def test_admin_puede_cambiar_preferencia_notificaciones(
    client: AsyncClient,
    auth_admin: dict,
    admin: Usuario,
):
    """Un administrador puede activar o desactivar la recepción de correos."""
    res = await client.patch(
        f"/usuarios/{admin.id}",
        json={"recibir_notificaciones_email": False},
        headers=auth_admin,
    )
    assert res.status_code == 200, res.text
    assert res.json()["recibir_notificaciones_email"] is False

    # Reactivar
    res_activar = await client.patch(
        f"/usuarios/{admin.id}",
        json={"recibir_notificaciones_email": True},
        headers=auth_admin,
    )
    assert res_activar.status_code == 200, res_activar.text
    assert res_activar.json()["recibir_notificaciones_email"] is True


@pytest.mark.asyncio
async def test_obtener_emails_administradores_filtra_por_preferencia(
    db: AsyncSession,
    admin: Usuario,
):
    """obtener_emails_administradores excluye administradores con notificaciones desactivadas."""
    admin_mudo = await factories.crear_usuario(
        db,
        username="admin_silencioso",
        rol=RolUsuario.ADMIN,
    )
    admin_mudo.recibir_notificaciones_email = False
    await db.commit()

    emails = await obtener_emails_administradores(db)
    assert admin.email in emails
    assert admin_mudo.email not in emails


@pytest.mark.asyncio
async def test_crear_pedido_solo_notifica_admins_con_notificaciones_activas(
    client: AsyncClient,
    db: AsyncSession,
    auth_catedra: dict,
    catedra: Catedra,
    template,
    admin: Usuario,
    mock_email: list[dict],
    perfil_capacidad,
):
    """Al crear un pedido y procesar el outbox, solo los admins con preferencia activa reciben correos."""
    admin_mudo = await factories.crear_usuario(
        db,
        username="admin_sin_mails",
        rol=RolUsuario.ADMIN,
    )
    admin_mudo.recibir_notificaciones_email = False
    await db.commit()

    payload = {
        "catedra_id": catedra.id,
        "template_id": template.id,
        "modelo_servicio": "iaas",
        "vigencia": _vigencia(),
        "descripcion_requerimientos": "Servidor de pruebas",
    }

    mock_email.clear()
    res = await client.post(
        "/pedidos/",
        json=payload,
        headers=auth_catedra | {"Idempotency-Key": "notif-pref-1"},
    )
    assert res.status_code == 201, res.text

    while await notificacion_service.procesar_uno(db):
        pass

    assert len(mock_email) >= 1
    destinatarios = [e for m in mock_email for e in m["destinatarios"]]
    assert admin.email in destinatarios
    assert admin_mudo.email not in destinatarios

