"""Baja lógica frente a la contabilidad de capacidad, métricas e historial.

Reescrito para la feature 004: la regla de fondo que estas pruebas verificaban
—lo dado de baja no ocupa capacidad— sigue vigente; lo que cambió es contra qué
se mide. Antes se medía contra la cuota declarada de la cátedra, que ya no
existe; ahora contra la capacidad real del clúster.
"""

from sqlalchemy import select

from app.models.pedido import EstadoPedido, PedidoHistorial
from app.services import capacidad_service
from tests import factories


async def test_servicio_dado_de_baja_no_consume_capacidad(
    client, db, proxmox, catedra, template, auth_admin
):
    """Lo dado de baja deja de contar como desplegado."""
    servicio = await factories.crear_servicio(
        db,
        catedra_id=catedra.id,
        template_id=template.id,
        proxmox_vmid="140",
        vcpus=4,
        ram_mb=4096,
        disk_gb=16,
    )

    antes = await capacidad_service.panorama(db)
    assert antes["desplegado"]["vcpus"] == 4
    assert antes["desplegado"]["ram_mb"] == 4096

    await client.delete(f"/servicios/{servicio.id}", headers=auth_admin)

    despues = await capacidad_service.panorama(db)
    assert despues["desplegado"]["vcpus"] == 0
    assert despues["desplegado"]["ram_mb"] == 0
    assert despues["desplegado"]["storage_gb"] == 0


async def test_crear_pedido_no_se_bloquea_por_consumo_acumulado(
    client, db, proxmox, catedra, usuario_catedra, template, auth_catedra
):
    """El cambio de modelo, visto desde la API.

    Bajo el modelo anterior este pedido daba 409 por cuota agotada. Ahora entra
    siempre: quién decide es el administrador al aprobarlo.
    """
    await factories.crear_servicio(
        db,
        catedra_id=catedra.id,
        template_id=template.id,
        proxmox_vmid="141",
        vcpus=4,
        ram_mb=4096,
        disk_gb=16,
    )

    respuesta = await client.post(
        "/pedidos/", json={"template_id": template.id}, headers=auth_catedra
    )
    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["estado"] == EstadoPedido.SOLICITADO.value


async def test_uso_informado_de_la_catedra_excluye_dados_de_baja(
    client, db, proxmox, catedra, template, auth_admin
):
    """El consumo que se le informa a la cátedra ignora las bajas."""
    servicio = await factories.crear_servicio(
        db, catedra_id=catedra.id, template_id=template.id, proxmox_vmid="142", vcpus=2
    )

    antes = await client.get(f"/catedras/{catedra.id}", headers=auth_admin)
    assert antes.json()["vcpus_en_uso"] == 2

    await client.delete(f"/servicios/{servicio.id}", headers=auth_admin)

    despues = await client.get(f"/catedras/{catedra.id}", headers=auth_admin)
    assert despues.json()["vcpus_en_uso"] == 0
    assert despues.json()["servicios_activos"] == 0


async def test_consumo_historico_de_la_catedra_sigue_reconstruible(
    client, db, proxmox, catedra, usuario_catedra, template, auth_admin
):
    """El registro sobrevive a la baja, con sus recursos asignados.

    Es lo que permite responder "cuánto consumió esta cátedra el cuatrimestre
    pasado" mucho después de que el contenedor dejó de existir.
    """
    servicio = await factories.crear_servicio(
        db,
        catedra_id=catedra.id,
        template_id=template.id,
        proxmox_vmid="145",
        vcpus=3,
        ram_mb=2048,
        disk_gb=8,
    )
    await client.delete(f"/servicios/{servicio.id}", headers=auth_admin)

    await db.refresh(servicio)
    assert servicio.deleted_at is not None, "la baja debe ser lógica, no física"
    # Los recursos que ocupó siguen registrados: sin esto el histórico se pierde.
    assert servicio.vcpus_asignados == 3
    assert servicio.ram_asignada_mb == 2048
    assert servicio.disk_asignado_gb == 8
    assert servicio.catedra_id == catedra.id


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
