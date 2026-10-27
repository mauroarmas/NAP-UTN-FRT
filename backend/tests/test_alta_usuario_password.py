"""Pruebas para alta de usuario con contraseña provisoria automática y envío por correo."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.usuario import Usuario
from tests import factories


@pytest.mark.asyncio
async def test_crear_usuario_genera_password_provisoria_y_envia_correo(
    client: AsyncClient,
    db: AsyncSession,
    auth_admin: dict,
    mock_email: list[dict],
):
    """El alta de usuario no requiere contraseña manual; genera una provisoria y la envía por correo."""
    catedra = await factories.crear_catedra(db, nombre="Sistemas Operativos")

    payload = {
        "username": "prof_alberto",
        "nombre": "Alberto Gómez",
        "email": "alberto.gomez@frt.utn.edu.ar",
        "rol": "catedra_admin",
        "catedra_ids": [catedra.id],
    }

    res = await client.post("/usuarios/", json=payload, headers=auth_admin)
    assert res.status_code == 201, res.text
    data = res.json()

    assert data["username"] == "prof_alberto"
    assert data["debe_cambiar_password"] is True
    assert data["recibir_notificaciones_email"] is True

    # La outbox despacha después del commit, desde el worker.
    from app.services.notificacion_service import procesar_uno
    assert mock_email == []
    await procesar_uno(db)
    assert len(mock_email) == 1
    email_enviado = mock_email[0]
    assert "alberto.gomez@frt.utn.edu.ar" in email_enviado["destinatarios"]
    assert "prof_alberto" in email_enviado["texto_plano"]

    # Extraer contraseña provisoria del texto plano del correo y verificar login
    # En el correo dice: "- Contraseña provisoria: <password>"
    lines = email_enviado["texto_plano"].splitlines()
    pwd_line = [l for l in lines if "Contraseña provisoria:" in l]
    assert pwd_line, "No se encontró la línea de contraseña provisoria en el correo"
    password_provisoria = pwd_line[0].split("Contraseña provisoria:")[1].strip()
    assert len(password_provisoria) >= 8

    # Probar login con esa contraseña provisoria
    login_res = await client.post(
        "/auth/login",
        data={"username": "prof_alberto", "password": password_provisoria},
    )
    assert login_res.status_code == 200
    token_data = login_res.json()
    assert token_data["estado"] == "onboarding"
    assert "access_token" not in token_data


@pytest.mark.asyncio
async def test_crear_usuario_sin_email_falla(
    client: AsyncClient,
    db: AsyncSession,
    auth_admin: dict,
):
    """El email es obligatorio al dar de alta un nuevo usuario."""
    catedra = await factories.crear_catedra(db, nombre="Redes de Información")

    payload = {
        "username": "prof_sin_mail",
        "nombre": "Sin Mail",
        "rol": "catedra_admin",
        "catedra_ids": [catedra.id],
    }

    res = await client.post("/usuarios/", json=payload, headers=auth_admin)
    assert res.status_code in (400, 422)


@pytest.mark.asyncio
async def test_crear_catedra_admin_sin_catedras_falla(
    client: AsyncClient,
    auth_admin: dict,
):
    """Un responsable de cátedra debe tener al menos una cátedra asignada."""
    payload = {
        "username": "prof_sin_cat",
        "nombre": "Sin Cátedra",
        "email": "sincat@frt.utn.edu.ar",
        "rol": "catedra_admin",
        "catedra_ids": [],
    }

    res = await client.post("/usuarios/", json=payload, headers=auth_admin)
    assert res.status_code == 400
    assert "Asigná al menos una cátedra" in res.json()["detail"]["mensaje"]

