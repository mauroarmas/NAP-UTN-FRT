"""Aislamiento entre cátedras con una persona que tiene varias.

Todo el multi-inquilinato del portal descansaba en comparar contra un único
``usuario.catedra_id``. Al pasar a un conjunto, cada listado y cada verificación
de permiso cambia de "es mi cátedra" a "está entre mis cátedras": un cambio
mecánico pero de superficie amplia, donde cualquier punto omitido es una fuga de
datos entre cátedras.

Esta prueba recorre **todos** los endpoints de listado con la misma sesión, para
que "no me olvidé de ninguno" sea verificable y no una promesa. Si mañana se
agrega un listado nuevo, sumarlo acá es más barato que descubrir la fuga.
"""

from app.models.servicio import Servicio
from tests import factories


async def test_ve_las_dos_catedras_propias(client, usuario_multicatedra):
    r = await client.get("/catedras/mias", headers=usuario_multicatedra.headers)

    assert r.status_code == 200, r.text
    nombres = {c["nombre"] for c in r.json()}
    assert nombres == {"Propia A", "Propia B"}


async def test_el_listado_de_catedras_no_muestra_la_ajena(
    client, usuario_multicatedra
):
    r = await client.get("/catedras/", headers=usuario_multicatedra.headers)

    assert r.status_code == 200, r.text
    assert all(c["nombre"] != "Ajena" for c in r.json())


async def test_pedidos_cubre_ambas_propias_y_ninguna_ajena(
    client, usuario_multicatedra
):
    r = await client.get("/pedidos/", headers=usuario_multicatedra.headers)

    assert r.status_code == 200, r.text
    catedras_devueltas = {p["catedra_id"] for p in r.json()}
    propias = {c.id for c in usuario_multicatedra.propias}
    assert catedras_devueltas == propias
    assert usuario_multicatedra.ajena.id not in catedras_devueltas


async def test_servicios_cubre_ambas_propias_y_ninguna_ajena(
    client, usuario_multicatedra
):
    r = await client.get("/servicios/", headers=usuario_multicatedra.headers)

    assert r.status_code == 200, r.text
    catedras_devueltas = {s["catedra_id"] for s in r.json()}
    assert catedras_devueltas == {c.id for c in usuario_multicatedra.propias}


async def test_metricas_resumen_no_filtra_la_ajena(client, usuario_multicatedra, db):
    ajenos = (
        (
            await db.execute(
                Servicio.__table__.select().where(
                    Servicio.catedra_id == usuario_multicatedra.ajena.id
                )
            )
        )
        .mappings()
        .all()
    )
    ids_ajenos = {s["id"] for s in ajenos}

    r = await client.get("/metricas/resumen", headers=usuario_multicatedra.headers)

    assert r.status_code == 200, r.text
    devueltos = {s["servicio_id"] for s in r.json()}
    assert not (devueltos & ids_ajenos), "se filtró un servicio de una cátedra ajena"


async def test_detalle_de_catedra_ajena_da_403(client, usuario_multicatedra):
    r = await client.get(
        f"/catedras/{usuario_multicatedra.ajena.id}",
        headers=usuario_multicatedra.headers,
    )

    assert r.status_code == 403, r.text


async def test_detalle_de_pedido_ajeno_da_403(client, db, usuario_multicatedra):
    ajenos = (
        (
            await db.execute(
                Servicio.__table__.select().where(
                    Servicio.catedra_id == usuario_multicatedra.ajena.id
                )
            )
        )
        .mappings()
        .all()
    )
    pedido_ajeno = ajenos[0]["pedido_id"]

    r = await client.get(
        f"/pedidos/{pedido_ajeno}", headers=usuario_multicatedra.headers
    )

    assert r.status_code == 403, r.text


async def test_detalle_de_servicio_ajeno_da_403(client, db, usuario_multicatedra):
    ajenos = (
        (
            await db.execute(
                Servicio.__table__.select().where(
                    Servicio.catedra_id == usuario_multicatedra.ajena.id
                )
            )
        )
        .mappings()
        .all()
    )

    r = await client.get(
        f"/servicios/{ajenos[0]['id']}", headers=usuario_multicatedra.headers
    )

    assert r.status_code == 403, r.text


async def test_historial_de_metricas_ajeno_da_403(client, db, usuario_multicatedra):
    ajenos = (
        (
            await db.execute(
                Servicio.__table__.select().where(
                    Servicio.catedra_id == usuario_multicatedra.ajena.id
                )
            )
        )
        .mappings()
        .all()
    )

    r = await client.get(
        f"/metricas/{ajenos[0]['id']}/historial",
        headers=usuario_multicatedra.headers,
    )

    assert r.status_code == 403, r.text


async def test_no_puede_pedir_a_nombre_de_una_catedra_ajena(
    client, usuario_multicatedra
):
    r = await client.post(
        "/pedidos/",
        json={
            "template_id": usuario_multicatedra.template.id,
            "catedra_id": usuario_multicatedra.ajena.id,
        },
        headers=usuario_multicatedra.headers,
    )

    assert r.status_code == 403, r.text


async def test_con_varias_catedras_hay_que_indicar_cual(client, usuario_multicatedra):
    """Sin cátedra explícita el sistema no adivina: pide que se indique."""
    r = await client.post(
        "/pedidos/",
        json={"template_id": usuario_multicatedra.template.id},
        headers=usuario_multicatedra.headers,
    )

    assert r.status_code == 400, r.text


async def test_la_capacidad_del_cluster_es_solo_para_admin(
    client, usuario_multicatedra
):
    """El panorama del clúster es dominio del administrador."""
    r = await client.get("/capacidad/", headers=usuario_multicatedra.headers)

    assert r.status_code == 403, r.text
