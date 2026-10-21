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
from tests.capacity_helpers import seleccion
import pytest
from sqlalchemy import select
from app.models.metrica import MetricaSnapshot


async def test_ve_las_dos_catedras_propias(client, usuario_multicatedra):
    r = await client.get("/catedras/mias", headers=usuario_multicatedra.headers)

    assert r.status_code == 200, r.text
    nombres = {c["nombre"] for c in r.json()}
    assert nombres == {"Propia A", "Propia B"}


@pytest.mark.parametrize('suffix', ['/metricas', '/historial', '/acceso', '/consola', '/status'])
async def test_every_sensitive_service_route_denies_foreign_before_io(client, db, usuario_multicatedra, proxmox, monkeypatch, suffix):
    foreign = await db.scalar(select(Servicio).where(Servicio.catedra_id == usuario_multicatedra.ajena.id))
    calls = []

    def track(*args, **kwargs):
        calls.append(args)
        return {'status': 'running'}

    monkeypatch.setattr(proxmox, 'get_lxc_status', track)
    response = await client.get(f'/servicios/{foreign.id}' + suffix, headers=usuario_multicatedra.headers)
    assert response.status_code == 403, response.text
    assert foreign.hostname not in response.text
    assert not calls


async def test_last_metric_is_not_exposed_to_foreign_teacher(client, db, usuario_multicatedra):
    foreign = await db.scalar(select(Servicio).where(Servicio.catedra_id == usuario_multicatedra.ajena.id))
    db.add(MetricaSnapshot(servicio_id=foreign.id, cpu_usage_percent=73, ram_usage_mb=111,
                          disk_usage_gb=2, net_in_bytes=1234, net_out_bytes=4567))
    await db.commit()
    response = await client.get(f'/metricas/{foreign.id}/ultimo', headers=usuario_multicatedra.headers)
    assert response.status_code == 403
    assert '1234' not in response.text


async def test_previous_session_loses_scope_on_next_request(client, db, usuario_multicatedra):
    owned = usuario_multicatedra.propias[0]
    service = await db.scalar(select(Servicio).where(Servicio.catedra_id == owned.id))
    owned.titular_id = usuario_multicatedra.ajeno.id
    await db.commit()
    response = await client.get(f'/servicios/{service.id}', headers=usuario_multicatedra.headers)
    assert response.status_code == 403


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
            "modelo_servicio": "iaas", "vigencia": seleccion(usuario_multicatedra.template)['vigencia'],
        },
        headers=usuario_multicatedra.headers | {'Idempotency-Key':'foreign-category-create'},
    )

    assert r.status_code == 403, r.text


async def test_con_varias_catedras_hay_que_indicar_cual(client, usuario_multicatedra):
    """Sin cátedra explícita el sistema no adivina: pide que se indique."""
    r = await client.post(
        "/pedidos/",
        json={"template_id": usuario_multicatedra.template.id, "modelo_servicio":"iaas",
              "vigencia":seleccion(usuario_multicatedra.template)['vigencia']},
        headers=usuario_multicatedra.headers | {'Idempotency-Key':'ambiguous-category-create'},
    )

    assert r.status_code == 422, r.text
    assert r.json()['detail']['codigo'] == 'catedra_requerida'


async def test_la_capacidad_del_cluster_es_solo_para_admin(
    client, usuario_multicatedra
):
    """El panorama del clúster es dominio del administrador."""
    r = await client.get("/capacidad/", headers=usuario_multicatedra.headers)

    assert r.status_code == 403, r.text
