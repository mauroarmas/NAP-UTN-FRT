"""Las respuestas que anidan relaciones no pueden depender de la sesión tibia.

Estas pruebas existen por un defecto real: `GET /auth/me` y `GET /pedidos/`
devolvían 500 en producción mientras la suite pasaba en verde. Las respuestas
sumaron campos anidados que salen de relaciones de carga diferida, y en
SQLAlchemy async resolverlas **durante la serialización** revienta con
`MissingGreenlet`.

Por qué no se notaba: en una prueba, el objeto suele quedar en el mapa de
identidad de la sesión con la relación ya cargada por una consulta anterior, así
que el atributo se lee sin ir a la base. En producción cada petición trae una
sesión fría y la carga diferida sí ocurre.

`expunge_all()` es lo que reproduce esa sesión fría. Cualquier endpoint que
anide una relación en su respuesta debería sumarse acá.
"""

from app.models.pedido import EstadoPedido
from tests import factories


async def test_listado_de_pedidos_con_sesion_fria(
    client, db, catedra, usuario_catedra, template, auth_catedra
):
    await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario_catedra.id,
        template_id=template.id,
        estado=EstadoPedido.SOLICITADO,
    )
    db.expunge_all()

    r = await client.get("/pedidos/", headers=auth_catedra)

    assert r.status_code == 200, r.text
    assert r.json()[0]["catedra"]["nombre"] == catedra.nombre


async def test_detalle_de_pedido_con_sesion_fria(
    client, db, catedra, usuario_catedra, template, auth_catedra
):
    pedido = await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario_catedra.id,
        template_id=template.id,
        estado=EstadoPedido.SOLICITADO,
    )
    pedido_id = pedido.id
    db.expunge_all()

    r = await client.get(f"/pedidos/{pedido_id}", headers=auth_catedra)

    assert r.status_code == 200, r.text
    assert r.json()["catedra"]["nombre"] == catedra.nombre


async def test_alta_de_pedido_con_sesion_fria(
    client, db, catedra, usuario_catedra, template, auth_catedra
):
    db.expunge_all()

    r = await client.post(
        "/pedidos/", json={"template_id": template.id}, headers=auth_catedra
    )

    assert r.status_code == 201, r.text
    assert r.json()["catedra"]["nombre"] == catedra.nombre


async def test_auth_me_con_sesion_fria(
    client, db, catedra, usuario_catedra, auth_catedra
):
    db.expunge_all()

    r = await client.get("/auth/me", headers=auth_catedra)

    assert r.status_code == 200, r.text
    assert [c["nombre"] for c in r.json()["catedras"]] == [catedra.nombre]


async def test_listado_de_usuarios_con_sesion_fria(client, db, catedra, admin, auth_admin):
    db.expunge_all()

    r = await client.get("/usuarios/", headers=auth_admin)

    assert r.status_code == 200, r.text


async def test_listado_de_catedras_con_sesion_fria(client, db, catedra, auth_admin):
    db.expunge_all()

    r = await client.get("/catedras/", headers=auth_admin)

    assert r.status_code == 200, r.text
    assert r.json()[0]["titular"]["username"] == "profe"


async def test_listado_de_servicios_con_sesion_fria(
    client, db, catedra, template, auth_catedra
):
    await factories.crear_servicio(
        db, catedra_id=catedra.id, template_id=template.id, proxmox_vmid="900"
    )
    db.expunge_all()

    r = await client.get("/servicios/", headers=auth_catedra)

    assert r.status_code == 200, r.text
