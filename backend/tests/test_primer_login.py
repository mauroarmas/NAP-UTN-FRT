"""Pruebas para cambio obligatorio de contraseña en el primer inicio de sesión."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.usuario import Usuario, RolUsuario
from app.utils.security import get_password_hash
from tests.test_auth_contrato_009 import ingresar, csrf


@pytest.mark.asyncio
async def test_cambiar_password_inicial_exitoso(
    client: AsyncClient,
    db: AsyncSession,
):
    """Un usuario con debe_cambiar_password=True actualiza su clave, se desactiva el flag y puede ingresar con la nueva."""
    usuario = Usuario(
        username="prof_inicial",
        email="inicial@frt.utn.edu.ar",
        nombre="Profesor Inicial",
        password_hash=get_password_hash("Provisoria123!"),
        rol=RolUsuario.CATEDRA_ADMIN,
        activo=True,
        debe_cambiar_password=True,
        recibir_notificaciones_email=True,
    )
    db.add(usuario)
    await db.commit()
    await db.refresh(usuario)

    # Token para el usuario con clave provisoria
    assert (await ingresar(client, usuario, 'Provisoria123!')).json()['estado'] == 'onboarding'
    headers = await csrf(client)

    # Intentar cambiar la contraseña por una válida
    nueva_clave = "MiNuevaPasswordSegura2026!"
    res = await client.post(
        "/auth/cambiar-password-inicial",
        json={"nueva_password": nueva_clave},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["usuario"]["debe_cambiar_password"] is False
    assert data["estado"] == "operativo"

    # Verificar que la clave vieja ya no funciona
    login_vieja = await client.post(
        "/auth/login",
        data={"username": "prof_inicial", "password": "Provisoria123!"},
    )
    assert login_vieja.status_code == 401

    # Verificar que la nueva clave sí funciona
    login_nueva = await client.post(
        "/auth/login",
        data={"username": "prof_inicial", "password": nueva_clave},
    )
    assert login_nueva.status_code == 200
    assert login_nueva.json()["estado"] == "operativo"
    assert "access_token" not in login_nueva.json()


@pytest.mark.asyncio
async def test_cambiar_password_inicial_longitud_corta_falla(
    client: AsyncClient,
    db: AsyncSession,
):
    """La nueva contraseña debe tener al menos 8 caracteres."""
    usuario = Usuario(
        username="prof_corta",
        email="corta@frt.utn.edu.ar",
        nombre="Profesor Clave Corta",
        password_hash=get_password_hash("Provisoria123!"),
        rol=RolUsuario.CATEDRA_ADMIN,
        activo=True,
        debe_cambiar_password=True,
    )
    db.add(usuario)
    await db.commit()
    await db.refresh(usuario)

    assert (await ingresar(client, usuario, 'Provisoria123!')).json()['estado'] == 'onboarding'
    headers = await csrf(client)

    res = await client.post(
        "/auth/cambiar-password-inicial",
        json={"nueva_password": "corta"},
        headers=headers,
    )
    assert res.status_code == 422
    assert "8 caracteres" in res.json()["detail"]["mensaje"]


@pytest.mark.asyncio
async def test_cambiar_password_inicial_sin_autenticar_falla(
    client: AsyncClient,
):
    """No se puede invocar el endpoint sin autenticación."""
    res = await client.post(
        "/auth/cambiar-password-inicial",
        json={"nueva_password": "PasswordValida123!"},
    )
    assert res.status_code == 401

