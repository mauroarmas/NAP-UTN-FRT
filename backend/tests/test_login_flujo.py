"""Flujo de inicio de sesión de punta a punta.

Ninguna prueba cubría el camino que el frontend recorre al entrar —login y
después `/auth/me`—, y por eso pasó inadvertido que `/auth/me` devolviera 500:
el token se emitía bien, así que "login" parecía funcionar, pero la sesión nunca
llegaba a establecerse.

La causa concreta: `UsuarioResponse` sumó las cátedras a cargo, que son una
relación de carga diferida. Resolverla durante la serialización revienta en
contexto async, y el error aparece recién cuando FastAPI lee el atributo — no al
construir el objeto.
"""

from app.models.usuario import RolUsuario
from tests import factories


async def _login(client, username, password="secreto123"):
    return await client.post(
        "/auth/login",
        data={"username": username, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )


async def test_login_devuelve_token(client, db, usuario_catedra):
    r = await _login(client, "profe")

    assert r.status_code == 200, r.text
    assert r.json()["access_token"]


async def test_el_flujo_completo_de_entrada_funciona(client, db, catedra, usuario_catedra):
    """Login seguido de `/auth/me`, que es exactamente lo que hace el frontend."""
    token = (await _login(client, "profe")).json()["access_token"]

    me = await client.get(
        "/auth/me", headers={"Authorization": f"Bearer {token}"}
    )

    assert me.status_code == 200, me.text
    assert me.json()["username"] == "profe"


async def test_auth_me_incluye_las_catedras_a_cargo(
    client, db, catedra, usuario_catedra, auth_catedra
):
    """El Sidebar las usa para saber si mostrar el selector de cátedra."""
    me = await client.get("/auth/me", headers=auth_catedra)

    assert me.status_code == 200, me.text
    assert [c["nombre"] for c in me.json()["catedras"]] == [catedra.nombre]


async def test_auth_me_de_alguien_sin_catedras_no_falla(client, db):
    """Un administrador puede no tener ninguna: la lista vacía es válida."""
    admin = await factories.crear_usuario(db, "solo_admin", rol=RolUsuario.ADMIN)
    token = (await _login(client, "solo_admin")).json()["access_token"]

    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert me.status_code == 200, me.text
    assert me.json()["catedras"] == []


async def test_usuarios_me_devuelve_lo_mismo_que_auth_me(
    client, db, catedra, usuario_catedra, auth_catedra
):
    """Son dos puertas al mismo dato; que digan cosas distintas sería un defecto."""
    uno = await client.get("/auth/me", headers=auth_catedra)
    otro = await client.get("/usuarios/me", headers=auth_catedra)

    assert uno.status_code == otro.status_code == 200
    assert uno.json() == otro.json()


async def test_credenciales_invalidas_dan_401(client, db, usuario_catedra):
    r = await _login(client, "profe", password="equivocada")

    assert r.status_code == 401, r.text


async def test_un_usuario_desactivado_no_entra(client, db, usuario_catedra):
    usuario_catedra.activo = False
    await db.commit()

    r = await _login(client, "profe")

    assert r.status_code == 403, r.text
