"""Pruebas para preferencias de notificación por correo de los administradores."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catedra import Catedra
from app.models.usuario import Usuario, RolUsuario
from app.services.email_service import obtener_emails_administradores
from tests import factories


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
    # Crear un segundo admin con notificaciones apagadas
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
):
    """Al crear un pedido, solo los admins con preferencia activa reciben correos."""
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
        "vigencia_tipo": "anual",
        "descripcion_requerimientos": "Servidor de pruebas",
    }

    mock_email.clear()
    res = await client.post("/pedidos/", json=payload, headers=auth_catedra)
    assert res.status_code == 201, res.text

    assert len(mock_email) >= 1
    destinatarios = mock_email[-1]["destinatarios"]
    assert admin.email in destinatarios
    assert admin_mudo.email not in destinatarios

