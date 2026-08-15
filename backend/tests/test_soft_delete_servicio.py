"""US2 — baja lógica de servicios (FR-007 a FR-010)."""

from sqlalchemy import select

from app.models.servicio import EstadoServicio, Servicio
from tests import factories
from tests.fakes import ProxmoxFalla, ocupar


async def _servicio(db, catedra, template, **kwargs):
    return await factories.crear_servicio(
        db, catedra_id=catedra.id, template_id=template.id, **kwargs
    )


async def test_baja_libera_el_contenedor_y_conserva_la_fila(
    client, db, proxmox, catedra, template, auth_admin
):
    """US2 esc. 1 / FR-007, FR-008 — se libera en Proxmox y la fila permanece."""
    servicio = await _servicio(db, catedra, template, proxmox_vmid="120")
    proxmox.estados[120] = "running"

    r = await client.delete(f"/servicios/{servicio.id}", headers=auth_admin)

    assert r.status_code == 200, r.text
    assert r.json()["deleted_at"] is not None
    assert ("pve1", 120) in proxmox.eliminados

    # La fila NO se borra: sigue consultable con sus datos de consumo
    fila = (
        await db.execute(select(Servicio).where(Servicio.id == servicio.id))
    ).scalar_one()
    assert fila.deleted_at is not None
    assert fila.vcpus_asignados == 1
    assert fila.ram_asignada_mb == 512


async def test_servicio_dado_de_baja_desaparece_de_listados(
    client, db, proxmox, catedra, template, auth_admin
):
    """US2 esc. 2 / FR-009 — fuera de los listados y 404 en el detalle."""
    servicio = await _servicio(db, catedra, template, proxmox_vmid="121")
    await client.delete(f"/servicios/{servicio.id}", headers=auth_admin)

    listado = await client.get("/servicios/", headers=auth_admin)
    assert listado.status_code == 200
    assert all(s["id"] != servicio.id for s in listado.json())

    detalle = await client.get(f"/servicios/{servicio.id}", headers=auth_admin)
    assert detalle.status_code == 404

    estado = await client.get(f"/servicios/{servicio.id}/status", headers=auth_admin)
    assert estado.status_code == 404


async def test_fallo_de_proxmox_no_marca_la_baja(
    client, db, proxmox, catedra, template, auth_admin
):
    """FR-010 — si no se pudo liberar el recurso real, no se marca como dado de baja."""
    servicio = await _servicio(db, catedra, template, proxmox_vmid="122")
    # El contenedor sigue vivo en el clúster: es lo que hace que el fallo importe.
    proxmox.recursos.append(ocupar(122, servicio.hostname))
    proxmox.fallar_delete = ProxmoxFalla("el nodo no responde")

    r = await client.delete(f"/servicios/{servicio.id}", headers=auth_admin)

    assert r.status_code == 502, r.text
    await db.refresh(servicio)
    assert servicio.deleted_at is None, (
        "no debe marcarse la baja si el contenedor sigue vivo en el clúster"
    )


async def test_doble_baja_es_idempotente(
    client, db, proxmox, catedra, template, auth_admin
):
    """US2 esc. 5 — repetir la baja no falla."""
    servicio = await _servicio(db, catedra, template, proxmox_vmid="123")

    r1 = await client.delete(f"/servicios/{servicio.id}", headers=auth_admin)
    assert r1.status_code == 200
    eliminados_tras_primera = len(proxmox.eliminados)

    r2 = await client.delete(f"/servicios/{servicio.id}", headers=auth_admin)
    assert r2.status_code == 200, r2.text
    assert "ya estaba dado de baja" in r2.json()["message"]
    # No se vuelve a golpear Proxmox
    assert len(proxmox.eliminados) == eliminados_tras_primera


async def test_servicio_dado_de_baja_no_admite_operaciones_de_ciclo_de_vida(
    client, db, proxmox, catedra, template, auth_admin
):
    """Un registro dado de baja es inaccesible también para start/stop (FR-009)."""
    servicio = await _servicio(db, catedra, template, proxmox_vmid="124")
    await client.delete(f"/servicios/{servicio.id}", headers=auth_admin)
    proxmox.detenidos.clear()
    proxmox.iniciados.clear()

    stop = await client.post(f"/servicios/{servicio.id}/stop", headers=auth_admin)
    start = await client.post(f"/servicios/{servicio.id}/start", headers=auth_admin)

    assert stop.status_code == 404
    assert start.status_code == 404
    assert proxmox.detenidos == []
    assert proxmox.iniciados == []


async def test_pedido_dado_de_baja_no_se_puede_desplegar(
    client, db, proxmox, catedra, usuario_catedra, template, auth_admin
):
    """El despliegue inicial tampoco alcanza registros dados de baja."""
    from app.models.pedido import EstadoPedido

    pedido = await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario_catedra.id,
        template_id=template.id,
        estado=EstadoPedido.APROBADO,
    )
    await client.delete(f"/pedidos/{pedido.id}", headers=auth_admin)

    r = await client.post(f"/servicios/desplegar/{pedido.id}", headers=auth_admin)

    assert r.status_code == 404
    assert proxmox.creados == []


async def test_contenedor_borrado_desde_proxmox_se_puede_dar_de_baja(
    client, db, proxmox, catedra, template, auth_admin
):
    """
    Si el contenedor ya no existe, el recurso está liberado: la baja procede.

    Sin esto el registro quedaba trabado — Proxmox falla al operar sobre un
    VMID inexistente y el 502 impedía cerrarlo desde el portal para siempre.
    """
    servicio = await _servicio(db, catedra, template, proxmox_vmid="125")
    # No figura en el clúster (alguien lo borró desde Proxmox) y operar sobre él falla.
    proxmox.fallar_delete = ProxmoxFalla("Configuration file 'nodes/pve1/lxc/125.conf' does not exist")

    r = await client.delete(f"/servicios/{servicio.id}", headers=auth_admin)

    assert r.status_code == 200, r.text
    await db.refresh(servicio)
    assert servicio.deleted_at is not None


async def test_baja_no_procede_si_no_se_puede_verificar_el_cluster(
    client, db, proxmox, catedra, template, auth_admin
):
    """Ante la duda, conservador: sin poder verificar, el registro no se cierra."""
    servicio = await _servicio(db, catedra, template, proxmox_vmid="126")
    proxmox.fallar_delete = ProxmoxFalla("timeout")
    proxmox.fallar_recursos = ProxmoxFalla("clúster inalcanzable")

    r = await client.delete(f"/servicios/{servicio.id}", headers=auth_admin)

    assert r.status_code == 502, r.text
    await db.refresh(servicio)
    assert servicio.deleted_at is None


async def test_servicio_sin_vmid_se_da_de_baja_sin_tocar_proxmox(
    client, db, proxmox, catedra, template, auth_admin
):
    """Un servicio que nunca llegó a desplegarse no requiere operación remota."""
    servicio = await _servicio(
        db, catedra, template, proxmox_vmid=None, estado=EstadoServicio.STOPPED
    )

    r = await client.delete(f"/servicios/{servicio.id}", headers=auth_admin)

    assert r.status_code == 200, r.text
    assert proxmox.eliminados == []
    await db.refresh(servicio)
    assert servicio.deleted_at is not None
