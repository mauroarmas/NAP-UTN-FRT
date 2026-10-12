import pytest
from app.models.pedido import EstadoPedido, ModeloServicio, VigenciaTipo, Pedido
from app.models.servicio import EstadoServicio, Servicio
from tests import factories

NODO = [
    {
        "node": "pve1",
        "status": "online",
        "cpu": 0.1,
        "maxcpu": 8,
        "maxmem": 16 * 1024**3,
        "maxdisk": 100 * 1024**3,
    }
]


@pytest.fixture(autouse=True)
def cluster(proxmox):
    proxmox.nodos = NODO
    return proxmox


async def test_aprobar_asigna_template_a_pedido_sin_template(
    client, db, catedra, usuario_catedra, template, auth_admin
):
    """Un pedido SaaS/PaaS que nació sin template recibe su template definitivo al aprobar."""
    pedido = await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario_catedra.id,
        template_id=None,
        estado=EstadoPedido.SOLICITADO,
        modelo_servicio=ModeloServicio.SAAS,
        descripcion_requerimientos="Moodle institucional para el cuatrimestre",
        vigencia_tipo=VigenciaTipo.PRIMER_CUATRIMESTRE,
    )

    r = await client.post(
        f"/pedidos/{pedido.id}/aprobar",
        json={"template_id": template.id},
        headers=auth_admin,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["estado"] == "aprobado"
    assert data["template_id"] == template.id
    assert data["reserva_vcpus"] == template.default_vcpus


async def test_aprobar_con_opciones_avanzadas_y_overrides(
    client, db, catedra, usuario_catedra, template, auth_admin
):
    """Las opciones avanzadas permiten overrides de computo y red."""
    pedido = await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario_catedra.id,
        template_id=template.id,
        estado=EstadoPedido.SOLICITADO,
    )

    opciones = {
        "nodo_destino": "pve1",
        "storage_pool": "local-zfs",
        "vlan_tag": 100,
        "override_vcpus": 4,
        "override_ram_mb": 4096,
        "override_disk_gb": 6,
    }

    r = await client.post(
        f"/pedidos/{pedido.id}/aprobar",
        json={"opciones_avanzadas": opciones},
        headers=auth_admin,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["estado"] == "aprobado"
    assert data["reserva_vcpus"] == 4
    assert data["reserva_ram_mb"] == 4096
    assert data["reserva_disk_gb"] == 6
    assert data["opciones_avanzadas"]["vlan_tag"] == 100


async def test_aprobar_con_despliegue_inmediato(
    client, db, catedra, usuario_catedra, template, auth_admin
):
    """Aprobar con desplegar_inmediatamente=True orquesta y crea el servicio de inmediato."""
    pedido = await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario_catedra.id,
        template_id=template.id,
        estado=EstadoPedido.SOLICITADO,
    )

    r = await client.post(
        f"/pedidos/{pedido.id}/aprobar",
        json={"desplegar_inmediatamente": True},
        headers=auth_admin,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["estado"] == "activo"
    assert data["servicio_id"] is not None

    servicio = await db.get(Servicio, data["servicio_id"])
    assert servicio is not None
    assert servicio.estado == EstadoServicio.RUNNING
    assert servicio.url_acceso is not None
    assert "http://" in servicio.url_acceso
    assert servicio.credenciales_acceso is not None

