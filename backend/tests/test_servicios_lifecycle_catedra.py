"""US1/US2/US3 (spec 003) — apagar, encender, reiniciar y consola sobre servicios propios."""

from app.models.servicio import EstadoServicio
from app.utils.security import create_access_token
from tests import factories
from tests.fakes import ocupar


async def _crear_servicio_de_otra_catedra(db, estado=EstadoServicio.RUNNING):
    """Servicio que pertenece a una cátedra distinta de la de los fixtures compartidos."""
    otra_catedra = await factories.crear_catedra(db, nombre="Otra Cátedra")
    template = await factories.crear_template(db, nombre="Template ajeno")
    return await factories.crear_servicio(
        db, catedra_id=otra_catedra.id, template_id=template.id, estado=estado
    )


async def _headers_de(usuario) -> dict:
    token = create_access_token({"sub": usuario.username, "rol": usuario.rol.value})
    return {"Authorization": f"Bearer {token}"}


# --- Apagar / encender: éxito para la cátedra dueña ---


async def test_catedra_apaga_su_propio_servicio(
    client, db, proxmox, catedra, template, auth_catedra
):
    servicio = await factories.crear_servicio(
        db, catedra_id=catedra.id, template_id=template.id, estado=EstadoServicio.RUNNING
    )

    r = await client.post(f"/servicios/{servicio.id}/stop", headers=auth_catedra)

    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "stopped"
    await db.refresh(servicio)
    assert servicio.estado == EstadoServicio.STOPPED
    assert (servicio.proxmox_node, int(servicio.proxmox_vmid)) in proxmox.detenidos


async def test_catedra_enciende_su_propio_servicio(
    client, db, proxmox, catedra, template, auth_catedra
):
    servicio = await factories.crear_servicio(
        db, catedra_id=catedra.id, template_id=template.id, estado=EstadoServicio.STOPPED
    )

    r = await client.post(f"/servicios/{servicio.id}/start", headers=auth_catedra)

    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "running"
    await db.refresh(servicio)
    assert servicio.estado == EstadoServicio.RUNNING


# --- Aislamiento entre cátedras (FR-005) ---


async def test_catedra_no_puede_apagar_servicio_ajeno(client, db, proxmox, auth_catedra):
    servicio_ajeno = await _crear_servicio_de_otra_catedra(db, estado=EstadoServicio.RUNNING)

    r = await client.post(f"/servicios/{servicio_ajeno.id}/stop", headers=auth_catedra)

    assert r.status_code == 403, r.text
    assert proxmox.detenidos == []
    await db.refresh(servicio_ajeno)
    assert servicio_ajeno.estado == EstadoServicio.RUNNING


async def test_catedra_no_puede_encender_servicio_ajeno(client, db, proxmox, auth_catedra):
    servicio_ajeno = await _crear_servicio_de_otra_catedra(db, estado=EstadoServicio.STOPPED)

    r = await client.post(f"/servicios/{servicio_ajeno.id}/start", headers=auth_catedra)

    assert r.status_code == 403, r.text
    assert proxmox.iniciados == []


# --- Estado inválido (FR-007) ---


async def test_apagar_servicio_ya_detenido_da_409(client, db, catedra, template, auth_catedra):
    servicio = await factories.crear_servicio(
        db, catedra_id=catedra.id, template_id=template.id, estado=EstadoServicio.STOPPED
    )

    r = await client.post(f"/servicios/{servicio.id}/stop", headers=auth_catedra)

    assert r.status_code == 409, r.text


async def test_encender_servicio_ya_corriendo_da_409(client, db, catedra, template, auth_catedra):
    servicio = await factories.crear_servicio(
        db, catedra_id=catedra.id, template_id=template.id, estado=EstadoServicio.RUNNING
    )

    r = await client.post(f"/servicios/{servicio.id}/start", headers=auth_catedra)

    assert r.status_code == 409, r.text


# --- Fallo de infraestructura simulado (Principio III) ---


async def test_fallo_al_apagar_da_502_sin_mutar_estado(
    client, db, proxmox, catedra, template, auth_catedra
):
    proxmox.fallar_stop = Exception("timeout de Proxmox")
    servicio = await factories.crear_servicio(
        db, catedra_id=catedra.id, template_id=template.id, estado=EstadoServicio.RUNNING
    )

    r = await client.post(f"/servicios/{servicio.id}/stop", headers=auth_catedra)

    assert r.status_code == 502, r.text
    await db.refresh(servicio)
    assert servicio.estado == EstadoServicio.RUNNING


async def test_fallo_al_encender_da_502_sin_mutar_estado(
    client, db, proxmox, catedra, template, auth_catedra
):
    proxmox.fallar_start = Exception("timeout de Proxmox")
    servicio = await factories.crear_servicio(
        db, catedra_id=catedra.id, template_id=template.id, estado=EstadoServicio.STOPPED
    )

    r = await client.post(f"/servicios/{servicio.id}/start", headers=auth_catedra)

    assert r.status_code == 502, r.text
    await db.refresh(servicio)
    assert servicio.estado == EstadoServicio.STOPPED


# --- Reiniciar (US2) ---


async def test_catedra_reinicia_su_propio_servicio(
    client, db, proxmox, catedra, template, auth_catedra
):
    servicio = await factories.crear_servicio(
        db, catedra_id=catedra.id, template_id=template.id, estado=EstadoServicio.RUNNING
    )

    r = await client.post(f"/servicios/{servicio.id}/restart", headers=auth_catedra)

    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "running"
    await db.refresh(servicio)
    assert servicio.estado == EstadoServicio.RUNNING
    assert (servicio.proxmox_node, int(servicio.proxmox_vmid)) in proxmox.reiniciados


async def test_catedra_no_puede_reiniciar_servicio_ajeno(client, db, proxmox, auth_catedra):
    servicio_ajeno = await _crear_servicio_de_otra_catedra(db, estado=EstadoServicio.RUNNING)

    r = await client.post(f"/servicios/{servicio_ajeno.id}/restart", headers=auth_catedra)

    assert r.status_code == 403, r.text
    assert proxmox.reiniciados == []


async def test_reiniciar_servicio_detenido_da_409(client, db, catedra, template, auth_catedra):
    servicio = await factories.crear_servicio(
        db, catedra_id=catedra.id, template_id=template.id, estado=EstadoServicio.STOPPED
    )

    r = await client.post(f"/servicios/{servicio.id}/restart", headers=auth_catedra)

    assert r.status_code == 409, r.text


async def test_fallo_al_reiniciar_da_502_sin_mutar_estado(
    client, db, proxmox, catedra, template, auth_catedra
):
    proxmox.fallar_reboot = Exception("timeout de Proxmox")
    servicio = await factories.crear_servicio(
        db, catedra_id=catedra.id, template_id=template.id, estado=EstadoServicio.RUNNING
    )

    r = await client.post(f"/servicios/{servicio.id}/restart", headers=auth_catedra)

    assert r.status_code == 502, r.text
    await db.refresh(servicio)
    assert servicio.estado == EstadoServicio.RUNNING


# --- Ticket de consola (US3, EN PAUSA) ---
#
# La consola embebida quedó en pausa (ver DUDAS-ENTREVISTA.md): hasta definir
# con la cátedra cómo debe gestionarse el acceso al contenedor, el ticket es
# solo para administrador y el frontend no lo usa. Estos tests fijan esa
# restricción para que no se reabra por accidente.


async def test_catedra_no_puede_pedir_ticket_de_consola_ni_de_su_propio_servicio(
    client, db, proxmox, catedra, template, auth_catedra
):
    servicio = await factories.crear_servicio(
        db, catedra_id=catedra.id, template_id=template.id, estado=EstadoServicio.RUNNING
    )

    r = await client.post(f"/servicios/{servicio.id}/console-ticket", headers=auth_catedra)

    assert r.status_code == 403, r.text


async def test_pedir_ticket_de_consola_con_servicio_detenido_da_409(
    client, db, catedra, template, auth_admin
):
    servicio = await factories.crear_servicio(
        db, catedra_id=catedra.id, template_id=template.id, estado=EstadoServicio.STOPPED
    )

    r = await client.post(f"/servicios/{servicio.id}/console-ticket", headers=auth_admin)

    assert r.status_code == 409, r.text


async def test_admin_obtiene_ticket_de_consola_de_un_servicio_en_ejecucion(
    client, db, proxmox, catedra, template, auth_admin
):
    servicio = await factories.crear_servicio(
        db, catedra_id=catedra.id, template_id=template.id, estado=EstadoServicio.RUNNING
    )

    r = await client.post(f"/servicios/{servicio.id}/console-ticket", headers=auth_admin)

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ticket"]
    assert body["expira_en_segundos"] > 0


async def test_base_de_consola_proxmox_es_solo_para_admin(client, auth_catedra, auth_admin):
    assert (await client.get("/servicios/consola/proxmox-base", headers=auth_catedra)).status_code == 403

    r = await client.get("/servicios/consola/proxmox-base", headers=auth_admin)
    assert r.status_code == 200, r.text
    assert r.json()["base_url"].startswith("https://")


# --- Paridad de administrador (FR-006) ---


async def test_admin_apaga_servicio_de_cualquier_catedra(client, db, proxmox, auth_admin):
    servicio_ajeno = await _crear_servicio_de_otra_catedra(db, estado=EstadoServicio.RUNNING)

    r = await client.post(f"/servicios/{servicio_ajeno.id}/stop", headers=auth_admin)

    assert r.status_code == 200, r.text


async def test_admin_reinicia_servicio_de_cualquier_catedra(client, db, proxmox, auth_admin):
    servicio_ajeno = await _crear_servicio_de_otra_catedra(db, estado=EstadoServicio.RUNNING)

    r = await client.post(f"/servicios/{servicio_ajeno.id}/restart", headers=auth_admin)

    assert r.status_code == 200, r.text


# --- Reconciliación con el estado real del clúster ---
#
# El registro del portal se desfasa cuando Proxmox se apaga y vuelve, o cuando
# alguien toca el contenedor por fuera. Proxmox es la fuente de verdad.


async def test_el_listado_corrige_el_estado_desfasado(
    client, db, proxmox, catedra, template, auth_catedra
):
    servicio = await factories.crear_servicio(
        db, catedra_id=catedra.id, template_id=template.id, estado=EstadoServicio.RUNNING
    )
    # En el clúster el contenedor está apagado: el registro quedó viejo.
    proxmox.recursos.append(ocupar(int(servicio.proxmox_vmid), servicio.hostname, status="stopped"))

    r = await client.get("/servicios/", headers=auth_catedra)

    assert r.status_code == 200, r.text
    fila = next(s for s in r.json() if s["id"] == servicio.id)
    assert fila["estado"] == "stopped"
    assert fila["estado_sincronizado"] is True
    await db.refresh(servicio)
    assert servicio.estado == EstadoServicio.STOPPED


async def test_listado_conserva_el_ultimo_estado_si_proxmox_no_responde(
    client, db, proxmox, catedra, template, auth_catedra
):
    proxmox.fallar_recursos = Exception("clúster inalcanzable")
    servicio = await factories.crear_servicio(
        db, catedra_id=catedra.id, template_id=template.id, estado=EstadoServicio.RUNNING
    )

    r = await client.get("/servicios/", headers=auth_catedra)

    assert r.status_code == 200, r.text
    fila = next(s for s in r.json() if s["id"] == servicio.id)
    assert fila["estado"] == "running"
    assert fila["estado_sincronizado"] is False


async def test_encender_servicio_que_proxmox_reporta_apagado(
    client, db, proxmox, catedra, template, auth_catedra
):
    """El caso que motivó el botón: el portal decía RUNNING y el contenedor estaba caído."""
    servicio = await factories.crear_servicio(
        db, catedra_id=catedra.id, template_id=template.id, estado=EstadoServicio.RUNNING
    )
    proxmox.recursos.append(ocupar(int(servicio.proxmox_vmid), servicio.hostname, status="stopped"))

    r = await client.post(f"/servicios/{servicio.id}/start", headers=auth_catedra)

    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "running"
    assert (servicio.proxmox_node, int(servicio.proxmox_vmid)) in proxmox.iniciados


async def test_apagar_servicio_que_proxmox_reporta_apagado_da_409(
    client, db, proxmox, catedra, template, auth_catedra
):
    servicio = await factories.crear_servicio(
        db, catedra_id=catedra.id, template_id=template.id, estado=EstadoServicio.RUNNING
    )
    proxmox.recursos.append(ocupar(int(servicio.proxmox_vmid), servicio.hostname, status="stopped"))

    r = await client.post(f"/servicios/{servicio.id}/stop", headers=auth_catedra)

    assert r.status_code == 409, r.text
    assert proxmox.detenidos == []
    await db.refresh(servicio)
    assert servicio.estado == EstadoServicio.STOPPED


async def test_contenedor_inexistente_se_marca_como_tal_en_el_listado(
    client, db, proxmox, catedra, template, auth_catedra
):
    """Borrado desde Proxmox: el registro sobrevive, pero avisa que quedó huérfano."""
    servicio = await factories.crear_servicio(
        db, catedra_id=catedra.id, template_id=template.id, estado=EstadoServicio.RUNNING
    )  # el clúster responde y no lo tiene

    fila = next(
        s for s in (await client.get("/servicios/", headers=auth_catedra)).json()
        if s["id"] == servicio.id
    )

    assert fila["existe_en_proxmox"] is False
    assert fila["estado_sincronizado"] is False
    await db.refresh(servicio)
    assert servicio.estado == EstadoServicio.RUNNING, "no se inventa un estado nuevo"


async def test_sin_respuesta_del_cluster_la_existencia_queda_indefinida(
    client, db, proxmox, catedra, template, auth_catedra
):
    """"No pudimos verificar" no es lo mismo que "no existe"."""
    proxmox.fallar_recursos = Exception("clúster inalcanzable")
    servicio = await factories.crear_servicio(
        db, catedra_id=catedra.id, template_id=template.id, estado=EstadoServicio.RUNNING
    )

    fila = next(
        s for s in (await client.get("/servicios/", headers=auth_catedra)).json()
        if s["id"] == servicio.id
    )

    assert fila["existe_en_proxmox"] is None


async def test_encender_servicio_en_error_lo_arranca(
    client, db, proxmox, catedra, template, auth_catedra
):
    """Encender es la salida natural también desde ERROR, no solo desde STOPPED."""
    servicio = await factories.crear_servicio(
        db, catedra_id=catedra.id, template_id=template.id, estado=EstadoServicio.ERROR
    )

    r = await client.post(f"/servicios/{servicio.id}/start", headers=auth_catedra)

    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "running"
