"""US1/US2/US3 (spec 003 + spec 009) — apagar, encender, reiniciar y consola sobre servicios propios."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.operacion_infraestructura import OperacionInfraestructura
from app.models.servicio import EstadoServicio
from app.worker import procesar_una
from tests import factories
from tests.capacity_helpers import materializado, perfil_capacidad  # noqa: F401
from tests.fakes import ocupar


@pytest.fixture(autouse=True)
def cluster(proxmox, perfil_capacidad):
    return proxmox


async def _crear_servicio_propio(
    db, proxmox, catedra, usuario, template, estado=EstadoServicio.RUNNING, vmid=210
):
    servicio, ledger = await materializado(
        db, proxmox, catedra, usuario, template, vmid=vmid
    )
    servicio.estado = estado
    if estado == EstadoServicio.RUNNING:
        ledger.vcpus_retenidos = servicio.vcpus_asignados
        ledger.ram_mb_retenida = servicio.ram_asignada_mb
        proxmox.estados[vmid] = "running"
        for r in proxmox.recursos:
            if int(r["vmid"]) == vmid:
                r["status"] = "running"
    else:
        ledger.vcpus_retenidos = 0
        ledger.ram_mb_retenida = 0
        proxmox.estados[vmid] = "stopped"
        for r in proxmox.recursos:
            if int(r["vmid"]) == vmid:
                r["status"] = "stopped"
    await db.commit()
    return servicio


async def _crear_servicio_de_otra_catedra(db, proxmox, template, estado=EstadoServicio.RUNNING, vmid=290):
    """Servicio que pertenece a una cátedra distinta de la de los fixtures compartidos."""
    otra_catedra = await factories.crear_catedra(db, nombre=f"Otra Cátedra {vmid}")
    otro_usuario = await factories.crear_usuario(db, username=f"otro_profe_{vmid}")
    return await _crear_servicio_propio(
        db, proxmox, otra_catedra, otro_usuario, template, estado=estado, vmid=vmid
    )


# --- Apagar / encender: éxito para la cátedra dueña ---


async def test_catedra_apaga_su_propio_servicio(
    client, engine, db, proxmox, catedra, usuario_catedra, template, auth_catedra
):
    servicio = await _crear_servicio_propio(
        db, proxmox, catedra, usuario_catedra, template, estado=EstadoServicio.RUNNING, vmid=211
    )

    r = await client.post(
        f"/servicios/{servicio.id}/stop",
        headers=auth_catedra | {"Idempotency-Key": f"stop-{uuid4()}"},
        json={},
    )

    assert r.status_code == 202, r.text
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await procesar_una(sessions, pve=proxmox)

    await db.refresh(servicio)
    assert servicio.estado == EstadoServicio.STOPPED
    assert (servicio.proxmox_node, int(servicio.proxmox_vmid)) in proxmox.detenidos


async def test_catedra_enciende_su_propio_servicio(
    client, engine, db, proxmox, catedra, usuario_catedra, template, auth_catedra
):
    servicio = await _crear_servicio_propio(
        db, proxmox, catedra, usuario_catedra, template, estado=EstadoServicio.STOPPED, vmid=212
    )

    r = await client.post(
        f"/servicios/{servicio.id}/start",
        headers=auth_catedra | {"Idempotency-Key": f"start-{uuid4()}"},
        json={},
    )

    assert r.status_code == 202, r.text
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await procesar_una(sessions, pve=proxmox)

    await db.refresh(servicio)
    assert servicio.estado == EstadoServicio.RUNNING


# --- Aislamiento entre cátedras (FR-005) ---


async def test_catedra_no_puede_apagar_servicio_ajeno(client, db, proxmox, template, auth_catedra):
    servicio_ajeno = await _crear_servicio_de_otra_catedra(
        db, proxmox, template, estado=EstadoServicio.RUNNING, vmid=291
    )

    r = await client.post(
        f"/servicios/{servicio_ajeno.id}/stop",
        headers=auth_catedra | {"Idempotency-Key": f"stop-{uuid4()}"},
        json={},
    )

    assert r.status_code == 403, r.text
    assert proxmox.detenidos == []
    await db.refresh(servicio_ajeno)
    assert servicio_ajeno.estado == EstadoServicio.RUNNING


async def test_catedra_no_puede_encender_servicio_ajeno(client, db, proxmox, template, auth_catedra):
    servicio_ajeno = await _crear_servicio_de_otra_catedra(
        db, proxmox, template, estado=EstadoServicio.STOPPED, vmid=292
    )

    r = await client.post(
        f"/servicios/{servicio_ajeno.id}/start",
        headers=auth_catedra | {"Idempotency-Key": f"start-{uuid4()}"},
        json={},
    )

    assert r.status_code == 403, r.text
    assert proxmox.iniciados == []


# --- Estado inválido (FR-007) ---


async def test_apagar_servicio_ya_detenido_da_409(
    client, db, proxmox, catedra, usuario_catedra, template, auth_catedra
):
    servicio = await _crear_servicio_propio(
        db, proxmox, catedra, usuario_catedra, template, estado=EstadoServicio.STOPPED, vmid=213
    )

    r = await client.post(
        f"/servicios/{servicio.id}/stop",
        headers=auth_catedra | {"Idempotency-Key": f"stop-{uuid4()}"},
        json={},
    )

    assert r.status_code == 409, r.text


async def test_encender_servicio_ya_corriendo_da_409(
    client, db, proxmox, catedra, usuario_catedra, template, auth_catedra
):
    servicio = await _crear_servicio_propio(
        db, proxmox, catedra, usuario_catedra, template, estado=EstadoServicio.RUNNING, vmid=214
    )

    r = await client.post(
        f"/servicios/{servicio.id}/start",
        headers=auth_catedra | {"Idempotency-Key": f"start-{uuid4()}"},
        json={},
    )

    assert r.status_code == 409, r.text


# --- Fallo de infraestructura simulado (Principio III) ---


async def test_fallo_al_apagar_da_502_sin_mutar_estado(
    client, engine, db, proxmox, catedra, usuario_catedra, template, auth_catedra
):
    servicio = await _crear_servicio_propio(
        db, proxmox, catedra, usuario_catedra, template, estado=EstadoServicio.RUNNING, vmid=215
    )
    proxmox.fallar_stop = Exception("timeout de Proxmox")

    r = await client.post(
        f"/servicios/{servicio.id}/stop",
        headers=auth_catedra | {"Idempotency-Key": f"stop-{uuid4()}"},
        json={},
    )

    assert r.status_code == 202, r.text
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await procesar_una(sessions, pve=proxmox)

    await db.refresh(servicio)
    assert servicio.estado == EstadoServicio.RUNNING
    op = await db.get(OperacionInfraestructura, UUID(r.json()["operation_id"]), populate_existing=True)
    assert op.estado in {"incierta", "fallida"}


async def test_fallo_al_encender_da_502_sin_mutar_estado(
    client, db, proxmox, catedra, usuario_catedra, template, auth_catedra
):
    servicio = await _crear_servicio_propio(
        db, proxmox, catedra, usuario_catedra, template, estado=EstadoServicio.STOPPED, vmid=216
    )
    proxmox.fallar_recursos = Exception("timeout de Proxmox")

    r = await client.post(
        f"/servicios/{servicio.id}/start",
        headers=auth_catedra | {"Idempotency-Key": f"start-{uuid4()}"},
        json={},
    )

    assert r.status_code == 502, r.text
    await db.refresh(servicio)
    assert servicio.estado == EstadoServicio.STOPPED


# --- La acción se confirma contra Proxmox antes de mutar el estado ---


async def test_encender_espera_a_que_la_tarea_de_proxmox_termine(
    client, engine, db, proxmox, catedra, usuario_catedra, template, auth_catedra
):
    servicio = await _crear_servicio_propio(
        db, proxmox, catedra, usuario_catedra, template, estado=EstadoServicio.STOPPED, vmid=217
    )

    r = await client.post(
        f"/servicios/{servicio.id}/start",
        headers=auth_catedra | {"Idempotency-Key": f"start-{uuid4()}"},
        json={},
    )

    assert r.status_code == 202, r.text
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await procesar_una(sessions, pve=proxmox)

    esperada = (servicio.proxmox_node, f"UPID:{servicio.proxmox_node}:task:start")
    assert esperada in proxmox.task_polls


async def test_apagar_espera_a_que_la_tarea_de_proxmox_termine(
    client, engine, db, proxmox, catedra, usuario_catedra, template, auth_catedra
):
    servicio = await _crear_servicio_propio(
        db, proxmox, catedra, usuario_catedra, template, estado=EstadoServicio.RUNNING, vmid=218
    )

    r = await client.post(
        f"/servicios/{servicio.id}/stop",
        headers=auth_catedra | {"Idempotency-Key": f"stop-{uuid4()}"},
        json={},
    )

    assert r.status_code == 202, r.text
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await procesar_una(sessions, pve=proxmox)

    esperada = (servicio.proxmox_node, f"UPID:{servicio.proxmox_node}:task:stop")
    assert esperada in proxmox.task_polls


async def test_fallo_dentro_de_la_tarea_al_encender_da_502_sin_mutar_estado(
    client, engine, db, proxmox, catedra, usuario_catedra, template, auth_catedra
):
    servicio = await _crear_servicio_propio(
        db, proxmox, catedra, usuario_catedra, template, estado=EstadoServicio.STOPPED, vmid=219
    )
    proxmox.configure_task(
        "pve1",
        "UPID:pve1:task:start",
        [{"status": "stopped", "exitstatus": "ERROR: no se pudo asignar la red al contenedor"}],
    )

    r = await client.post(
        f"/servicios/{servicio.id}/start",
        headers=auth_catedra | {"Idempotency-Key": f"start-{uuid4()}"},
        json={},
    )

    assert r.status_code == 202, r.text
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await procesar_una(sessions, pve=proxmox)

    await db.refresh(servicio)
    assert servicio.estado == EstadoServicio.STOPPED
    op = await db.get(OperacionInfraestructura, UUID(r.json()["operation_id"]), populate_existing=True)
    assert op.estado in {"incierta", "fallida"}


async def test_el_resumen_atrasado_del_cluster_no_deshace_un_arranque(
    client, engine, db, proxmox, catedra, usuario_catedra, template, auth_catedra
):
    """Encender y refrescar no puede devolver la fila a "Detenido"."""
    servicio = await _crear_servicio_propio(
        db, proxmox, catedra, usuario_catedra, template, estado=EstadoServicio.STOPPED, vmid=220
    )

    r = await client.post(
        f"/servicios/{servicio.id}/start",
        headers=auth_catedra | {"Idempotency-Key": f"start-{uuid4()}"},
        json={},
    )
    assert r.status_code == 202, r.text
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await procesar_una(sessions, pve=proxmox)
    await db.refresh(servicio)

    proxmox.retraso_resumen = True
    listado = await client.get("/servicios/", headers=auth_catedra)
    fila = next(s for s in listado.json() if s["id"] == servicio.id)
    assert fila["estado"] == "running", "el resumen atrasado revirtió el arranque"


# --- Reiniciar (US2) ---


async def test_catedra_reinicia_su_propio_servicio(
    client, engine, db, proxmox, catedra, usuario_catedra, template, auth_catedra
):
    servicio = await _crear_servicio_propio(
        db, proxmox, catedra, usuario_catedra, template, estado=EstadoServicio.RUNNING, vmid=221
    )

    r = await client.post(
        f"/servicios/{servicio.id}/restart",
        headers=auth_catedra | {"Idempotency-Key": f"restart-{uuid4()}"},
        json={},
    )

    assert r.status_code == 202, r.text
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await procesar_una(sessions, pve=proxmox)

    await db.refresh(servicio)
    assert servicio.estado == EstadoServicio.RUNNING
    assert (servicio.proxmox_node, int(servicio.proxmox_vmid)) in proxmox.reiniciados


async def test_catedra_no_puede_reiniciar_servicio_ajeno(client, db, proxmox, template, auth_catedra):
    servicio_ajeno = await _crear_servicio_de_otra_catedra(
        db, proxmox, template, estado=EstadoServicio.RUNNING, vmid=293
    )

    r = await client.post(
        f"/servicios/{servicio_ajeno.id}/restart",
        headers=auth_catedra | {"Idempotency-Key": f"restart-{uuid4()}"},
        json={},
    )

    assert r.status_code == 403, r.text
    assert proxmox.reiniciados == []


async def test_reiniciar_servicio_detenido_da_409(
    client, db, proxmox, catedra, usuario_catedra, template, auth_catedra
):
    servicio = await _crear_servicio_propio(
        db, proxmox, catedra, usuario_catedra, template, estado=EstadoServicio.STOPPED, vmid=222
    )

    r = await client.post(
        f"/servicios/{servicio.id}/restart",
        headers=auth_catedra | {"Idempotency-Key": f"restart-{uuid4()}"},
        json={},
    )

    assert r.status_code == 409, r.text


async def test_fallo_al_reiniciar_da_502_sin_mutar_estado(
    client, engine, db, proxmox, catedra, usuario_catedra, template, auth_catedra
):
    servicio = await _crear_servicio_propio(
        db, proxmox, catedra, usuario_catedra, template, estado=EstadoServicio.RUNNING, vmid=223
    )
    proxmox.fallar_reboot = Exception("timeout de Proxmox")

    r = await client.post(
        f"/servicios/{servicio.id}/restart",
        headers=auth_catedra | {"Idempotency-Key": f"restart-{uuid4()}"},
        json={},
    )

    assert r.status_code == 202, r.text
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await procesar_una(sessions, pve=proxmox)

    await db.refresh(servicio)
    assert servicio.estado == EstadoServicio.RUNNING
    op = await db.get(OperacionInfraestructura, UUID(r.json()["operation_id"]), populate_existing=True)
    assert op.estado in {"incierta", "fallida"}


# --- Ticket de consola (US3, EN PAUSA) ---


async def test_consola_general_retirada_para_catedra(client, auth_catedra):
    r = await client.get("/servicios/consola/proxmox-base", headers=auth_catedra)
    assert r.status_code == 405, r.text
    assert "url" not in r.json()


async def test_consola_general_retirada_para_admin(client, auth_admin):
    r = await client.get("/servicios/consola/proxmox-base", headers=auth_admin)
    assert r.status_code == 405, r.text
    assert "url" not in r.json()
