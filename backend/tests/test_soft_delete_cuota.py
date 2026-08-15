"""US2 — cuota, métricas e historial frente a la baja lógica (FR-011, FR-012)."""

from sqlalchemy import select

from app.models.pedido import EstadoPedido, PedidoHistorial
from app.services.pedido_service import verificar_cuota
from tests import factories


async def test_servicio_dado_de_baja_no_consume_cuota(
    client, db, proxmox, catedra, template, auth_admin
):
    """FR-012 / SC-005 — la cuota se libera al dar de baja."""
    servicio = await factories.crear_servicio(
        db,
        catedra_id=catedra.id,
        template_id=template.id,
        proxmox_vmid="140",
        vcpus=4,
        ram_mb=4096,
        disk_gb=16,
    )
    # Con el servicio vigente la cátedra está al tope de su cuota
    antes = await verificar_cuota(db, catedra.id, template)
    assert antes["dentro_de_cuota"] is False

    await client.delete(f"/servicios/{servicio.id}", headers=auth_admin)

    despues = await verificar_cuota(db, catedra.id, template)
    assert despues["dentro_de_cuota"] is True
    assert despues["uso_actual"]["vcpus"] == 0
    assert despues["uso_actual"]["ram_mb"] == 0


async def test_crear_pedido_vuelve_a_ser_posible_tras_la_baja(
    client, db, proxmox, catedra, usuario_catedra, template, auth_admin, auth_catedra
):
    """El efecto observable de FR-012 desde la API."""
    servicio = await factories.crear_servicio(
        db,
        catedra_id=catedra.id,
        template_id=template.id,
        proxmox_vmid="141",
        vcpus=4,
        ram_mb=4096,
        disk_gb=16,
    )

    bloqueado = await client.post(
        "/pedidos/", json={"template_id": template.id}, headers=auth_catedra
    )
    assert bloqueado.status_code == 409, "la cuota debería estar agotada"

    await client.delete(f"/servicios/{servicio.id}", headers=auth_admin)

    permitido = await client.post(
        "/pedidos/", json={"template_id": template.id}, headers=auth_catedra
    )
    assert permitido.status_code == 201, permitido.text


async def test_uso_informado_de_la_catedra_excluye_dados_de_baja(
    client, db, proxmox, catedra, template, auth_admin
):
    """FR-012 — el uso informado en el detalle de cátedra ignora las bajas."""
    servicio = await factories.crear_servicio(
        db, catedra_id=catedra.id, template_id=template.id, proxmox_vmid="142", vcpus=2
    )

    antes = await client.get(f"/catedras/{catedra.id}", headers=auth_admin)
    assert antes.json()["vcpus_en_uso"] == 2

    await client.delete(f"/servicios/{servicio.id}", headers=auth_admin)

    despues = await client.get(f"/catedras/{catedra.id}", headers=auth_admin)
    assert despues.json()["vcpus_en_uso"] == 0
    assert despues.json()["servicios_activos"] == 0


async def test_historial_del_pedido_sobrevive_a_la_baja(
    client, db, proxmox, catedra, usuario_catedra, template, auth_admin
):
    """FR-011 / SC-003 — el consumo histórico sigue reconstruible."""
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
            estado_anterior="en_revision",
            estado_nuevo="rechazado",
            comentario="sin capacidad este cuatrimestre",
            usuario_id=usuario_catedra.id,
        )
    )
    await db.commit()

    await client.delete(f"/pedidos/{pedido.id}", headers=auth_admin)

    filas = (
        (
            await db.execute(
                select(PedidoHistorial).where(PedidoHistorial.pedido_id == pedido.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(filas) == 1
    assert filas[0].comentario == "sin capacidad este cuatrimestre"


async def test_resumen_de_metricas_excluye_dados_de_baja(
    client, db, proxmox, catedra, template, auth_admin
):
    """Los servicios dados de baja no se siguen midiendo."""
    servicio = await factories.crear_servicio(
        db, catedra_id=catedra.id, template_id=template.id, proxmox_vmid="143"
    )

    await client.delete(f"/servicios/{servicio.id}", headers=auth_admin)

    r = await client.get("/metricas/resumen", headers=auth_admin)
    assert r.status_code == 200, r.text
    assert all(s["servicio_id"] != servicio.id for s in r.json())


async def test_captura_masiva_ignora_dados_de_baja(
    client, db, proxmox, catedra, template, auth_admin
):
    """La captura periódica no debe medir recursos ya liberados."""
    from app.services.metricas_service import capturar_todos_los_servicios

    servicio = await factories.crear_servicio(
        db, catedra_id=catedra.id, template_id=template.id, proxmox_vmid="144"
    )
    await client.delete(f"/servicios/{servicio.id}", headers=auth_admin)

    resultado = await capturar_todos_los_servicios(db)

    assert resultado.get("capturados", 0) == 0
