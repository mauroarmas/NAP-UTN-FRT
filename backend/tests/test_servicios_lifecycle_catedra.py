"""US1/US2/US3 (spec 003) — apagar, encender, reiniciar y consola sobre servicios propios."""

from app.models.servicio import EstadoServicio
from tests import factories
from tests.fakes import ocupar


async def _crear_servicio_de_otra_catedra(db, estado=EstadoServicio.RUNNING):
    """Servicio que pertenece a una cátedra distinta de la de los fixtures compartidos."""
    otra_catedra = await factories.crear_catedra(db, nombre="Otra Cátedra")
    template = await factories.crear_template(db, nombre="Template ajeno")
    return await factories.crear_servicio(
        db, catedra_id=otra_catedra.id, template_id=template.id, estado=estado
    )



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


# --- La acción se confirma contra Proxmox antes de responder ---
#
# `start`/`stop`/`reboot` devuelven un identificador de tarea y vuelven al
# instante. Si el portal respondiera ahí, diría "running" sobre un contenedor
# que todavía está arrancando —y un fallo dentro de la tarea sería invisible.


async def test_encender_espera_a_que_la_tarea_de_proxmox_termine(
    client, db, proxmox, catedra, template, auth_catedra
):
    servicio = await factories.crear_servicio(
        db, catedra_id=catedra.id, template_id=template.id, estado=EstadoServicio.STOPPED
    )

    r = await client.post(f"/servicios/{servicio.id}/start", headers=auth_catedra)

    assert r.status_code == 200, r.text
    esperada = (servicio.proxmox_node, f"UPID:{servicio.proxmox_node}:task:start")
    assert esperada in proxmox.tasks_esperadas


async def test_apagar_espera_a_que_la_tarea_de_proxmox_termine(
    client, db, proxmox, catedra, template, auth_catedra
):
    servicio = await factories.crear_servicio(
        db, catedra_id=catedra.id, template_id=template.id, estado=EstadoServicio.RUNNING
    )

    r = await client.post(f"/servicios/{servicio.id}/stop", headers=auth_catedra)

    assert r.status_code == 200, r.text
    esperada = (servicio.proxmox_node, f"UPID:{servicio.proxmox_node}:task:stop")
    assert esperada in proxmox.tasks_esperadas


async def test_fallo_dentro_de_la_tarea_al_encender_da_502_sin_mutar_estado(
    client, db, proxmox, catedra, template, auth_catedra
):
    # La llamada devuelve el task id sin problemas: el error recién aparece al
    # esperar su resultado. Sin la espera, este fallo no llegaba a la cátedra.
    proxmox.fallar_task = Exception("no se pudo asignar la red al contenedor")
    servicio = await factories.crear_servicio(
        db, catedra_id=catedra.id, template_id=template.id, estado=EstadoServicio.STOPPED
    )

    r = await client.post(f"/servicios/{servicio.id}/start", headers=auth_catedra)

    assert r.status_code == 502, r.text
    await db.refresh(servicio)
    assert servicio.estado == EstadoServicio.STOPPED


async def test_el_resumen_atrasado_del_cluster_no_deshace_un_arranque(
    client, db, proxmox, catedra, template, auth_catedra
):
    """Encender y refrescar no puede devolver la fila a "Detenido".

    `cluster/resources` tarda unos segundos en reflejar el arranque. Cuando la
    reconciliación le creía a ese resumen, el listado inmediato posterior al
    encendido revertía el estado y la acción parecía no haber ocurrido.
    """
    servicio = await factories.crear_servicio(
        db, catedra_id=catedra.id, template_id=template.id, estado=EstadoServicio.STOPPED
    )
    proxmox.recursos.append(
        ocupar(int(servicio.proxmox_vmid), servicio.hostname,
               node=servicio.proxmox_node, status="stopped")
    )
    proxmox.retraso_resumen = True

    r = await client.post(f"/servicios/{servicio.id}/start", headers=auth_catedra)
    assert r.status_code == 200, r.text

    listado = await client.get("/servicios/", headers=auth_catedra)
    fila = next(s for s in listado.json() if s["id"] == servicio.id)
    assert fila["estado"] == "running", "el resumen atrasado revirtió el arranque"


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
# La consola embebida se descartó (enmienda constitucional v3.0.0). Proxmox no
# acepta API tokens para el WebSocket de consola y exige un ticket de sesión, así
# que el portal no puede hacer de proxy: el relay conectaba y autenticaba, pero la
# sesión moría sin transmitir. El acceso pasa a resolverse derivando a la consola
# de Proxmox, para ambos roles, como única excepción nombrada al Principio I.
#
# Estos tests fijan el alcance nuevo: la derivación existe para los dos roles, y
# el portal sigue verificando la pertenencia antes de ofrecerla.


async def test_consola_general_retirada_para_catedra(client, auth_catedra):
    r = await client.get('/servicios/consola/proxmox-base', headers=auth_catedra)
    assert r.status_code == 405, r.text
    assert 'url' not in r.json()


async def test_consola_general_retirada_para_admin(client, auth_admin):
    r = await client.get('/servicios/consola/proxmox-base', headers=auth_admin)
    assert r.status_code == 405, r.text
    assert 'url' not in r.json()
