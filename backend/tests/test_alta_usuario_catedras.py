"""Alta de usuario con sus cátedras en una sola operación.

Antes había que crear la persona y después acordarse de asignarle sus materias:
dos pasos, y el segundo es el que se olvida. Ahora es un solo acto — y por eso
tiene que ser atómico: crear el usuario y dejarlo con menos cátedras de las
pedidas sería peor que no crearlo, porque nadie se entera.
"""

from app.models.catedra import Catedra
from app.models.usuario import RolUsuario
from tests import factories


async def test_alta_con_varias_catedras(client, db, auth_admin):
    a = await factories.crear_catedra(db, nombre="Álgebra")
    b = await factories.crear_catedra(db, nombre="Física")

    r = await client.post(
        "/usuarios/",
        json={
            "username": "mgomez",
            "nombre": "M. Gómez",
            "password": "secreto123",
            "rol": "catedra_admin",
            "catedra_ids": [a.id, b.id],
        },
        headers=auth_admin,
    )

    assert r.status_code == 201, r.text
    # El resumen vuelve en la respuesta: sin él hay que ir a buscar a otra
    # pantalla si el alta hizo lo que se pidió.
    nombres = {c["nombre"] for c in r.json()["catedras"]}
    assert nombres == {"Álgebra", "Física"}


async def test_las_catedras_quedan_a_nombre_del_nuevo_usuario(client, db, auth_admin):
    catedra = await factories.crear_catedra(db, nombre="Química")

    r = await client.post(
        "/usuarios/",
        json={
            "username": "quim",
            "nombre": "Q. Uno",
            "password": "secreto123",
            "catedra_ids": [catedra.id],
        },
        headers=auth_admin,
    )

    await db.refresh(catedra)
    assert catedra.titular_id == r.json()["id"]


async def test_alta_sin_catedras_se_rechaza(client, auth_admin):
    """Un responsable de cátedra sin cátedras no puede hacer nada."""
    r = await client.post(
        "/usuarios/",
        json={
            "username": "vacio",
            "nombre": "Sin Cátedras",
            "password": "secreto123",
            "rol": "catedra_admin",
            "catedra_ids": [],
        },
        headers=auth_admin,
    )

    assert r.status_code == 400, r.text


async def test_un_admin_puede_no_tener_catedras(client, auth_admin):
    r = await client.post(
        "/usuarios/",
        json={
            "username": "otro_admin",
            "nombre": "Otro Admin",
            "password": "secreto123",
            "rol": "admin",
            "catedra_ids": [],
        },
        headers=auth_admin,
    )

    assert r.status_code == 201, r.text


async def test_catedra_ya_tomada_no_crea_el_usuario(client, db, auth_admin):
    """Atomicidad: si una cátedra no está disponible, no se crea nada.

    Es el escenario del admin que busca, se distrae y confirma más tarde, o el
    de dos administradores trabajando a la vez.
    """
    titular = await factories.crear_usuario(db, "ya_titular")
    ocupada = await factories.crear_catedra(
        db, nombre="Ocupada", titular_id=titular.id
    )
    libre = await factories.crear_catedra(db, nombre="Libre")

    r = await client.post(
        "/usuarios/",
        json={
            "username": "nuevo",
            "nombre": "Nuevo",
            "password": "secreto123",
            "catedra_ids": [libre.id, ocupada.id],
        },
        headers=auth_admin,
    )

    assert r.status_code == 409, r.text
    assert r.json()["detail"]["codigo"] == "catedras_ya_asignadas"
    # Dice cuál y de quién, para poder rehacer la elección sin adivinar.
    assert r.json()["detail"]["catedras_no_disponibles"][0]["nombre"] == "Ocupada"

    listado = await client.get("/usuarios/", headers=auth_admin)
    assert all(u["username"] != "nuevo" for u in listado.json()), (
        "el usuario no debe existir si la operación falló"
    )
    await db.refresh(libre)
    assert libre.titular_id is None, "la cátedra libre tampoco debe quedar asignada"


async def test_catedra_inexistente_da_404(client, auth_admin):
    r = await client.post(
        "/usuarios/",
        json={
            "username": "fantasma",
            "nombre": "Fantasma",
            "password": "secreto123",
            "catedra_ids": [9999],
        },
        headers=auth_admin,
    )

    assert r.status_code == 404, r.text


async def test_editar_reasigna_la_titularidad(client, db, auth_admin):
    """La lista enviada es la titularidad completa tras la edición."""
    persona = await factories.crear_usuario(db, "reasignable")
    una = await factories.crear_catedra(db, nombre="Una", titular_id=persona.id)
    otra = await factories.crear_catedra(db, nombre="Otra")

    r = await client.patch(
        f"/usuarios/{persona.id}",
        json={"catedra_ids": [otra.id]},
        headers=auth_admin,
    )

    assert r.status_code == 200, r.text
    await db.refresh(una)
    await db.refresh(otra)
    assert una.titular_id is None, "la que salió de la lista queda sin titular"
    assert otra.titular_id == persona.id


async def test_desactivar_con_catedras_a_cargo_da_409(client, db, auth_admin):
    """Sus servicios seguirían consumiendo recursos sin nadie a quien preguntarle."""
    persona = await factories.crear_usuario(db, "con_catedras")
    await factories.crear_catedra(db, nombre="A cargo", titular_id=persona.id)

    r = await client.patch(
        f"/usuarios/{persona.id}", json={"activo": False}, headers=auth_admin
    )

    assert r.status_code == 409, r.text
    assert r.json()["detail"]["codigo"] == "catedras_sin_responsable"
    assert r.json()["detail"]["catedras"][0]["nombre"] == "A cargo"
    await db.refresh(persona)
    assert persona.activo is True


async def test_desactivar_sin_catedras_procede(client, db, auth_admin):
    persona = await factories.crear_usuario(db, "sin_catedras")

    r = await client.patch(
        f"/usuarios/{persona.id}", json={"activo": False}, headers=auth_admin
    )

    assert r.status_code == 200, r.text
    assert r.json()["activo"] is False


async def test_una_catedra_no_puede_dar_de_alta_usuarios(client, auth_catedra):
    r = await client.post(
        "/usuarios/",
        json={"username": "x", "nombre": "X", "password": "secreto123"},
        headers=auth_catedra,
    )

    assert r.status_code == 403, r.text
