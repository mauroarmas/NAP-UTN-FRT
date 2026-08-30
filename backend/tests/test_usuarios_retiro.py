"""Retirar a una persona sin destruir su rastro.

Hasta esta feature `DELETE /usuarios/{id}` borraba la fila. Para cualquiera que
hubiera creado un pedido —o sea, para cualquier docente real— eso significaba
intentar dejar el pedido sin solicitante, algo que la base rechaza: la operación
terminaba en un 500 sin explicación y la única salida era tocar la base a mano.

El error no era un accidente: era la base defendiendo el historial académico
que el Principio V manda conservar. La corrección no es debilitar esa defensa
sino dejar de pelearse con ella — retirar pasa a ser una baja lógica.
"""

import pytest

from app.models.usuario import RolUsuario
from tests import factories


async def _con_pedido(db, catedra, usuario, template):
    return await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario.id,
        template_id=template.id,
    )


# --- T015: la regresión del defecto ---


async def test_retirar_a_alguien_con_pedidos_no_revienta(
    client, auth_admin, db, catedra, usuario_catedra, template
):
    """La prueba que hubiera evitado el 500."""
    await _con_pedido(db, catedra, usuario_catedra, template)
    # La titularidad bloquearía por otro motivo; acá se prueba el historial.
    catedra.titular_id = None
    await db.commit()

    r = await client.delete(f"/usuarios/{usuario_catedra.id}", headers=auth_admin)

    assert r.status_code != 500, "el 500 es exactamente el defecto que se corrige"
    assert r.status_code == 200


async def test_la_autoria_del_pedido_sobrevive(
    client, auth_admin, db, catedra, usuario_catedra, template
):
    """U3/FR-010: el pedido conserva quién lo pidió."""
    pedido = await _con_pedido(db, catedra, usuario_catedra, template)
    catedra.titular_id = None
    await db.commit()

    await client.delete(f"/usuarios/{usuario_catedra.id}", headers=auth_admin)

    await db.refresh(pedido)
    assert pedido.solicitante_id == usuario_catedra.id


# --- T016: baja lógica vs. borrado real ---


async def test_con_historial_queda_desactivado_y_la_fila_permanece(
    client, auth_admin, db, catedra, usuario_catedra, template
):
    await _con_pedido(db, catedra, usuario_catedra, template)
    catedra.titular_id = None
    await db.commit()

    r = await client.delete(f"/usuarios/{usuario_catedra.id}", headers=auth_admin)

    assert r.json()["resultado"] == "desactivado"
    await db.refresh(usuario_catedra)
    assert usuario_catedra.activo is False


async def test_sin_historial_la_fila_se_elimina(client, auth_admin, db):
    from app.models.usuario import Usuario

    virgen = await factories.crear_usuario(db, username="tipeo_mal")

    r = await client.delete(f"/usuarios/{virgen.id}", headers=auth_admin)

    assert r.json()["resultado"] == "eliminado"
    assert await db.get(Usuario, virgen.id) is None


async def test_la_respuesta_dice_cual_de_las_dos_cosas_paso(client, auth_admin, db):
    """US2 escenario 3: quien retira no tiene que saber en qué caso está."""
    virgen = await factories.crear_usuario(db, username="sin_nada")
    r = await client.delete(f"/usuarios/{virgen.id}", headers=auth_admin)
    assert r.status_code == 200
    assert r.json()["resultado"] in {"desactivado", "eliminado"}
    assert r.json()["mensaje"]


# --- T017: los guards ---


async def test_no_puedo_retirarme_a_mi_mismo(client, auth_admin, admin):
    r = await client.delete(f"/usuarios/{admin.id}", headers=auth_admin)
    assert r.status_code == 400


async def test_el_guard_del_ultimo_administrador_reconoce_el_caso(db, admin):
    """U6/FR-013, probado sobre el helper y no sobre el endpoint.

    El guard **no es alcanzable por la API**, y conviene que quede escrito por
    qué: para llamar al endpoint hay que ser administrador activo, y el chequeo
    de "no podés eliminarte a vos mismo" corre antes. Entonces quien llama es
    siempre un administrador activo distinto del objetivo — o sea que siempre
    existe otro administrador activo y la condición del guard nunca se cumple.

    Se conserva igual como defensa en profundidad: si mañana aparece otro camino
    que retire cuentas (un script de migración, una baja masiva, un cambio de
    rol), el sistema no puede quedarse sin nadie que lo administre. Lo que se
    prueba acá es que la condición se reconoce bien.
    """
    from app.services.usuario_service import es_ultimo_admin_activo

    # Único administrador activo del sistema.
    assert await es_ultimo_admin_activo(db, admin.id) is True

    # Con un segundo administrador activo, ya no es el último.
    otro = await factories.crear_usuario(db, username="admin2", rol=RolUsuario.ADMIN)
    assert await es_ultimo_admin_activo(db, admin.id) is False

    # Una cuenta dada de baja no cuenta como respaldo: no puede administrar nada.
    otro.activo = False
    await db.commit()
    assert await es_ultimo_admin_activo(db, admin.id) is True


async def test_una_catedra_no_dispara_el_guard_de_administrador(db, usuario_catedra):
    """El guard mira el rol: un responsable de cátedra nunca es "último admin"."""
    from app.services.usuario_service import es_ultimo_admin_activo

    assert await es_ultimo_admin_activo(db, usuario_catedra.id) is False


async def test_con_catedras_a_cargo_se_bloquea(
    client, auth_admin, catedra, usuario_catedra
):
    """U8: la cátedra quedaría sin responsable."""
    r = await client.delete(f"/usuarios/{usuario_catedra.id}", headers=auth_admin)
    assert r.status_code == 409
    assert r.json()["detail"]["codigo"] == "catedras_sin_responsable"


async def test_la_catedra_no_puede_retirar_a_nadie(client, auth_catedra, db):
    otro = await factories.crear_usuario(db, username="otro")
    r = await client.delete(f"/usuarios/{otro.id}", headers=auth_catedra)
    assert r.status_code == 403


# --- T018: visibilidad ---


async def test_una_persona_retirada_no_puede_entrar(
    client, auth_admin, db, catedra, usuario_catedra, template
):
    """U4/FR-011."""
    await _con_pedido(db, catedra, usuario_catedra, template)
    catedra.titular_id = None
    await db.commit()
    await client.delete(f"/usuarios/{usuario_catedra.id}", headers=auth_admin)

    r = await client.post(
        "/auth/login",
        data={"username": usuario_catedra.username, "password": "secreto123"},
    )
    assert r.status_code in (401, 403)


async def test_el_listado_oculta_a_las_retiradas(
    client, auth_admin, db, catedra, usuario_catedra, template
):
    """U5/FR-012: mismo criterio que el Principio V fija para pedidos y servicios."""
    await _con_pedido(db, catedra, usuario_catedra, template)
    catedra.titular_id = None
    await db.commit()
    await client.delete(f"/usuarios/{usuario_catedra.id}", headers=auth_admin)

    r = await client.get("/usuarios/", headers=auth_admin)
    assert usuario_catedra.id not in [u["id"] for u in r.json()]


async def test_se_pueden_pedir_incluyendo_las_bajas(
    client, auth_admin, db, catedra, usuario_catedra, template
):
    await _con_pedido(db, catedra, usuario_catedra, template)
    catedra.titular_id = None
    await db.commit()
    await client.delete(f"/usuarios/{usuario_catedra.id}", headers=auth_admin)

    r = await client.get("/usuarios/?incluir_bajas=true", headers=auth_admin)
    assert usuario_catedra.id in [u["id"] for u in r.json()]


async def test_el_detalle_por_id_sigue_resolviendo(
    client, auth_admin, db, catedra, usuario_catedra, template
):
    """El historial de un pedido tiene que poder mostrar quién lo pidió."""
    await _con_pedido(db, catedra, usuario_catedra, template)
    catedra.titular_id = None
    await db.commit()
    await client.delete(f"/usuarios/{usuario_catedra.id}", headers=auth_admin)

    r = await client.get(f"/usuarios/{usuario_catedra.id}", headers=auth_admin)
    assert r.status_code == 200
    assert r.json()["username"] == usuario_catedra.username


def _headers_de(usuario):
    from app.utils.security import create_access_token

    token = create_access_token({"sub": usuario.username, "rol": usuario.rol.value})
    return {"Authorization": f"Bearer {token}"}
