"""Baja lógica frente a la contabilidad de capacidad, métricas e historial."""

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.pedido import EstadoPedido, PedidoHistorial
from app.models.servicio import EstadoServicio
from app.services import capacidad_service
from app.worker import procesar_una
from tests import factories
from tests.capacity_helpers import GIB, materializado, perfil_capacidad  # noqa: F401
from tests.service_helpers import link_capacity_definition


@pytest.fixture(autouse=True)
def cluster(proxmox, perfil_capacidad):
    return proxmox


async def _servicio_desplegado(
    db, proxmox, catedra, usuario, template, vmid=140, vcpus=4, ram_mb=4096, disk_gb=16
):
    servicio, ledger = await materializado(
        db, proxmox, catedra, usuario, template, vmid=int(vmid), vcpus=vcpus
    )
    servicio.estado = EstadoServicio.RUNNING
    servicio.vcpus_asignados = vcpus
    servicio.ram_asignada_mb = ram_mb
    servicio.disk_asignado_gb = disk_gb
    servicio.asignacion_snapshot = {
        **servicio.asignacion_snapshot,
        "vcpus": vcpus,
        "ram_mb": ram_mb,
        "disk_gb": disk_gb,
    }
    ledger.vcpus_retenidos = vcpus
    ledger.ram_mb_retenida = ram_mb
    ledger.disk_bytes_retenidos = disk_gb * GIB
    proxmox.estados[int(vmid)] = "running"
    proxmox.configuraciones[("pve1", int(vmid))]["cores"] = vcpus
    proxmox.configuraciones[("pve1", int(vmid))]["memory"] = ram_mb
    proxmox.configuraciones[("pve1", int(vmid))]["rootfs"] = f"local-lvm:vm-{int(vmid)}-disk-0,size={disk_gb}G"
    for r in proxmox.recursos:
        if int(r["vmid"]) == int(vmid):
            r["status"] = "running"
            r["maxcpu"] = vcpus
            r["maxmem"] = ram_mb * 1024 * 1024
    await db.commit()
    return servicio


async def _baja_servicio(client, engine, db, proxmox, servicio_id, auth_admin):
    r = await client.delete(
        f"/servicios/{servicio_id}",
        headers=auth_admin | {"Idempotency-Key": f"del-srv-{uuid4()}"},
    )
    assert r.status_code == 202, r.text
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await procesar_una(sessions, pve=proxmox)
    await procesar_una(sessions, pve=proxmox)
    db.expire_all()
    return r


async def test_servicio_dado_de_baja_no_consume_capacidad(
    client, engine, db, proxmox, catedra, usuario_catedra, template, auth_admin
):
    """Lo dado de baja deja de contar como desplegado."""
    servicio = await _servicio_desplegado(
        db,
        proxmox,
        catedra,
        usuario_catedra,
        template,
        vmid=140,
        vcpus=4,
        ram_mb=4096,
        disk_gb=16,
    )

    antes = await capacidad_service.panorama(db)
    assert antes["desplegado"]["vcpus"] == 4
    assert antes["desplegado"]["ram_mb"] == 4096

    await _baja_servicio(client, engine, db, proxmox, servicio.id, auth_admin)

    despues = await capacidad_service.panorama(db)
    assert despues["desplegado"]["vcpus"] == 0
    assert despues["desplegado"]["ram_mb"] == 0
    assert despues["comprometido"]["vcpus"] == 0


async def test_crear_pedido_no_se_bloquea_por_consumo_acumulado(
    client, db, proxmox, catedra, usuario_catedra, admin, template, auth_catedra
):
    """El cambio de modelo, visto desde la API."""
    await link_capacity_definition(db, template, admin)
    await _servicio_desplegado(
        db,
        proxmox,
        catedra,
        usuario_catedra,
        template,
        vmid=141,
        vcpus=4,
        ram_mb=4096,
        disk_gb=16,
    )

    respuesta = await client.post(
        "/pedidos/",
        json={
            "template_id": template.id,
            "modelo_servicio": "iaas",
            "vigencia": {
                "tipo": "personalizado",
                "desde": "2026-11-01",
                "hasta": "2026-12-30",
            },
        },
        headers=auth_catedra | {"Idempotency-Key": f"ped-{uuid4()}"},
    )
    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["estado"] == EstadoPedido.SOLICITADO.value


async def test_uso_informado_de_la_catedra_excluye_dados_de_baja(
    client, engine, db, proxmox, catedra, usuario_catedra, template, auth_admin
):
    """El consumo que se le informa a la cátedra ignora las bajas."""
    catedra_id = catedra.id
    servicio = await _servicio_desplegado(
        db, proxmox, catedra, usuario_catedra, template, vmid=142, vcpus=2
    )

    antes = await client.get(f"/catedras/{catedra_id}", headers=auth_admin)
    assert antes.json()["vcpus_en_uso"] == 2

    await _baja_servicio(client, engine, db, proxmox, servicio.id, auth_admin)

    despues = await client.get(f"/catedras/{catedra_id}", headers=auth_admin)
    assert despues.json()["vcpus_en_uso"] == 0
    assert despues.json()["servicios_activos"] == 0


async def test_consumo_historico_de_la_catedra_sigue_reconstruible(
    client, engine, db, proxmox, catedra, usuario_catedra, template, auth_admin
):
    """El registro sobrevive a la baja, con sus recursos asignados."""
    catedra_id = catedra.id
    servicio = await _servicio_desplegado(
        db,
        proxmox,
        catedra,
        usuario_catedra,
        template,
        vmid=145,
        vcpus=3,
        ram_mb=2048,
        disk_gb=8,
    )
    await _baja_servicio(client, engine, db, proxmox, servicio.id, auth_admin)

    await db.refresh(servicio)
    assert servicio.deleted_at is not None, "la baja debe ser lógica, no física"
    assert servicio.vcpus_asignados == 3
    assert servicio.ram_asignada_mb == 2048
    assert servicio.disk_asignado_gb == 8
    assert servicio.catedra_id == catedra_id


async def test_historial_del_pedido_sobrevive_a_la_baja(
    client, db, proxmox, catedra, usuario_catedra, template, auth_admin
):
    """El historial de transiciones es de solo agregado."""
    pedido = await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario_catedra.id,
        template_id=template.id,
        estado=EstadoPedido.RECHAZADO,
    )
    db.add(
        PedidoHistorial(
            pedido_id=pedido.id,
            estado_anterior="solicitado",
            estado_nuevo="rechazado",
            comentario="sin capacidad este cuatrimestre",
            usuario_id=usuario_catedra.id,
        )
    )
    await db.commit()

    await client.delete(
        f"/pedidos/{pedido.id}",
        headers=auth_admin | {"Idempotency-Key": f"del-ped-{uuid4()}"},
    )

    filas = (
        (
            await db.execute(
                select(PedidoHistorial).where(PedidoHistorial.pedido_id == pedido.id)
            )
        )
        .scalars()
        .all()
    )
    assert any(f.comentario == "sin capacidad este cuatrimestre" for f in filas)


async def test_resumen_de_metricas_excluye_dados_de_baja(
    client, engine, db, proxmox, catedra, usuario_catedra, template, auth_admin
):
    """Los servicios dados de baja no se siguen midiendo."""
    servicio = await _servicio_desplegado(
        db, proxmox, catedra, usuario_catedra, template, vmid=143
    )

    await _baja_servicio(client, engine, db, proxmox, servicio.id, auth_admin)

    r = await client.get("/metricas/resumen", headers=auth_admin)
    assert r.status_code == 200, r.text
    assert all(s["servicio_id"] != servicio.id for s in r.json())


async def test_captura_masiva_ignora_dados_de_baja(
    client, engine, db, proxmox, catedra, usuario_catedra, template, auth_admin
):
    """La captura periódica no debe medir recursos ya liberados."""
    from app.services.metricas_service import capturar_todos_los_servicios

    servicio = await _servicio_desplegado(
        db, proxmox, catedra, usuario_catedra, template, vmid=144
    )
    await _baja_servicio(client, engine, db, proxmox, servicio.id, auth_admin)

    resultado = await capturar_todos_los_servicios(db)

    assert resultado.get("capturados", 0) == 0
