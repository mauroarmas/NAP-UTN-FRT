"""Un bloqueo tiene que decir cómo salir de él.

Al intentar dar de baja a un titular, el portal respondía: "Reasignalas o dalas
de baja antes de desactivar la cuenta." Dar la cátedra de baja **no** destrabab
nada — se verificó en el entorno real el 2026-08-29 — porque el bloqueo mira
quién es el titular sin importar si la cátedra sigue activa.

El bloqueo tiene razón: una cátedra dada de baja puede conservar servicios
corriendo, y esos servicios siguen necesitando responsable. El que estaba mal
era el consejo. Estas pruebas fijan las dos cosas: que el mensaje indique la
salida que funciona, y que el bloqueo siga aplicando aunque la cátedra esté
inactiva, para que nadie lo "optimice" más adelante.
"""

import pytest

from tests import factories


async def test_el_consejo_del_mensaje_realmente_destraba(
    client, auth_admin, db, catedra, usuario_catedra
):
    """FR-016: seguir el mensaje al pie de la letra tiene que funcionar."""
    r = await client.delete(f"/usuarios/{usuario_catedra.id}", headers=auth_admin)
    assert r.status_code == 409
    detalle = r.json()["detail"]
    assert detalle["codigo"] == "catedras_sin_responsable"
    assert [c["id"] for c in detalle["catedras"]] == [catedra.id]

    # Se hace exactamente lo que el mensaje indica: reasignar el titular.
    otro = await factories.crear_usuario(db, username="releva")
    catedra.titular_id = otro.id
    await db.commit()

    r2 = await client.delete(f"/usuarios/{usuario_catedra.id}", headers=auth_admin)
    assert r2.status_code == 200, "el consejo del mensaje no destrabó la operación"


async def test_el_mensaje_no_sugiere_dar_la_catedra_de_baja(
    client, auth_admin, catedra, usuario_catedra
):
    """La sugerencia vieja mandaba a un callejón sin salida."""
    r = await client.delete(f"/usuarios/{usuario_catedra.id}", headers=auth_admin)
    mensaje = r.json()["detail"]["mensaje"].lower()
    assert "reasign" in mensaje
    assert "dalas de baja" not in mensaje


async def test_el_mismo_mensaje_en_el_patch(
    client, auth_admin, catedra, usuario_catedra
):
    """Las dos puertas que sacan a alguien de circulación dicen lo mismo."""
    r = await client.patch(
        f"/usuarios/{usuario_catedra.id}", json={"activo": False}, headers=auth_admin
    )
    assert r.status_code == 409
    mensaje = r.json()["detail"]["mensaje"].lower()
    assert "reasign" in mensaje
    assert "dalas de baja" not in mensaje


async def test_el_bloqueo_sigue_con_la_catedra_dada_de_baja(
    client, auth_admin, db, catedra, usuario_catedra
):
    """FR-017: el guard NO debe filtrar por `activa`.

    Es la prueba que protege contra la "optimización" evidente: hacer que
    `catedras_de` ignore las cátedras inactivas parecería arreglar el mensaje,
    pero permitiría dar de baja al titular de una cátedra con contenedores
    encendidos y nadie a cargo.
    """
    catedra.activa = False
    await db.commit()

    r = await client.delete(f"/usuarios/{usuario_catedra.id}", headers=auth_admin)
    assert r.status_code == 409
    assert r.json()["detail"]["codigo"] == "catedras_sin_responsable"


async def test_una_catedra_inactiva_puede_tener_servicios_vivos(
    db, catedra, template, usuario_catedra
):
    """El hecho que justifica la regla anterior.

    Dar una cátedra de baja no detiene sus servicios: solo pide confirmación.
    Por eso una cátedra inactiva sigue necesitando responsable.
    """
    servicio = await factories.crear_servicio(
        db, catedra_id=catedra.id, template_id=template.id
    )
    catedra.activa = False
    await db.commit()

    await db.refresh(servicio)
    assert servicio.deleted_at is None
    assert servicio.proxmox_vmid is not None


async def test_sin_catedras_a_cargo_no_hay_bloqueo(client, auth_admin, db):
    """El bloqueo no debe aparecer donde no corresponde."""
    suelto = await factories.crear_usuario(db, username="sin_catedras")
    r = await client.delete(f"/usuarios/{suelto.id}", headers=auth_admin)
    assert r.status_code == 200
