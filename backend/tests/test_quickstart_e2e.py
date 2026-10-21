"""Validación End-to-End de los 6 escenarios de quickstart.md.

Cubre:
1. Flujo Principal IaaS (Creación, Aprobación y Aprovisionamiento)
2. Solicitud SaaS / PaaS con Opciones Avanzadas
3. Flujo de Negociación y Ajuste (REQUIERE_AJUSTE y Reenviar)
4. Rechazo Fundado con Motivo Obligatorio
5. ABM de Templates y Validación Constitucional de Capacidad (8 GB)
6. Autogestión de Servicios (Reinicio / Reboot y Métricas en Tiempo Real)
"""

import pytest
from app.models.pedido import EstadoPedido
from app.models.servicio import EstadoServicio
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


async def test_escenario_1_flujo_principal_iaas(client, auth_admin, auth_catedra, catedra, template, proxmox):
    """Escenario 1: Solicitud IaaS, evaluación y despliegue automático exitoso."""
    # 1. Docente envía solicitud IaaS
    resp_pedido = await client.post(
        "/pedidos/",
        json={
            "template_id": template.id,
            "modelo_servicio": "iaas",
            "descripcion_requerimientos": "Entorno de laboratorio básico Linux",
            "vigencia_tipo": "primer_cuatrimestre",
            "catedra_id": catedra.id,
        },
        headers=auth_catedra,
    )
    assert resp_pedido.status_code == 201
    pedido_data = resp_pedido.json()
    assert pedido_data["estado"] == EstadoPedido.SOLICITADO.value
    pedido_id = pedido_data["id"]

    # 2. Administrador consulta pedidos solicitados
    resp_listar = await client.get("/pedidos/?estado=solicitado", headers=auth_admin)
    assert resp_listar.status_code == 200
    ids = [p["id"] for p in resp_listar.json()]
    assert pedido_id in ids

    # 3. Administrador aprueba con despliegue automático
    resp_aprobar = await client.post(
        f"/pedidos/{pedido_id}/aprobar",
        json={"template_id": template.id, "desplegar_inmediatamente": True},
        headers=auth_admin,
    )
    assert resp_aprobar.status_code == 200, resp_aprobar.text
    aprobado = resp_aprobar.json()
    assert aprobado["estado"] == EstadoPedido.ACTIVO.value
    assert aprobado["servicio_id"] is not None

    # 4. Docente consulta sus servicios y verifica el aprovisionamiento
    resp_servicios = await client.get("/servicios/", headers=auth_catedra)
    assert resp_servicios.status_code == 200
    servicios = resp_servicios.json()
    assert any(s["id"] == aprobado["servicio_id"] for s in servicios)


async def test_escenario_2_saas_paas_opciones_avanzadas(client, auth_admin, auth_catedra, catedra, template, proxmox):
    """Escenario 2: Solicitud SaaS/PaaS con opciones avanzadas de red y almacenamiento."""
    # 1. Docente pide servicio SaaS
    resp_pedido = await client.post(
        "/pedidos/",
        json={
            "modelo_servicio": "saas",
            "descripcion_requerimientos": "Libro virtual interactivo para cátedra de Sistemas Operativos",
            "vigencia_tipo": "anual",
            "catedra_id": catedra.id,
        },
        headers=auth_catedra,
    )
    assert resp_pedido.status_code == 201
    pedido_id = resp_pedido.json()["id"]

    # 2. Administrador aprueba configurando opciones avanzadas en nodo online
    resp_aprobar = await client.post(
        f"/pedidos/{pedido_id}/aprobar",
        json={
            "template_id": template.id,
            "desplegar_inmediatamente": True,
            "opciones_avanzadas": {
                "nodo_destino": "pve1",
                "storage_pool": "local-zfs",
                "vlan_tag": 100,
            },
        },
        headers=auth_admin,
    )
    assert resp_aprobar.status_code == 200, resp_aprobar.text
    pedido_aprobado = resp_aprobar.json()
    assert pedido_aprobado["estado"] == EstadoPedido.ACTIVO.value

    # 3. Comprobar que el servicio tiene URL de acceso y credenciales
    servicio_id = pedido_aprobado["servicio_id"]
    resp_serv = await client.get(f"/servicios/{servicio_id}", headers=auth_catedra)
    assert resp_serv.status_code == 200
    s_data = resp_serv.json()
    assert s_data["url_acceso"] is not None
    assert s_data["credenciales_acceso"] is not None


async def test_escenario_3_negociacion_y_ajuste(client, auth_admin, auth_catedra, catedra, template):
    """Escenario 3: Ciclo de ajuste colaborativo (solicitar-ajuste y reenviar)."""
    # 1. Docente envía pedido
    resp = await client.post(
        "/pedidos/",
        json={
            "template_id": template.id,
            "modelo_servicio": "iaas",
            "descripcion_requerimientos": "Servidor con 64GB de RAM",
            "catedra_id": catedra.id,
        },
        headers=auth_catedra,
    )
    assert resp.status_code == 201
    pedido_id = resp.json()["id"]

    # 2. Administrador solicita ajuste
    resp_ajuste = await client.post(
        f"/pedidos/{pedido_id}/solicitar-ajuste",
        json={"observaciones": "Capacidad reducida en memoria RAM; se sugiere ajustar a 4GB."},
        headers=auth_admin,
    )
    assert resp_ajuste.status_code == 200
    assert resp_ajuste.json()["estado"] == EstadoPedido.REQUIERE_AJUSTE.value

    # 3. Docente reenvía el pedido ajustado
    resp_reenviar = await client.post(
        f"/pedidos/{pedido_id}/reenviar",
        json={"descripcion_requerimientos": "Ajustado a 4GB de RAM conforme a lo sugerido"},
        headers=auth_admin,
    )
    assert resp_reenviar.status_code == 200
    assert resp_reenviar.json()["estado"] == EstadoPedido.SOLICITADO.value


async def test_escenario_4_rechazo_fundado_obligatorio(client, auth_admin, auth_catedra, catedra, template):
    """Escenario 4: Rechazo requiere justificación escrita obligatoria."""
    # 1. Docente envía pedido
    resp = await client.post(
        "/pedidos/",
        json={"template_id": template.id, "catedra_id": catedra.id},
        headers=auth_catedra,
    )
    pedido_id = resp.json()["id"]

    # 2. Rechazo con cuerpo vacío debe fallar 422
    resp_vacio = await client.post(
        f"/pedidos/{pedido_id}/rechazar",
        json={},
        headers=auth_admin,
    )
    assert resp_vacio.status_code == 422

    # 3. Rechazo con motivo solo espacios debe fallar 400
    resp_espacios = await client.post(
        f"/pedidos/{pedido_id}/rechazar",
        json={"motivo": "    "},
        headers=auth_admin,
    )
    assert resp_espacios.status_code == 400
    assert "motivo" in resp_espacios.json()["detail"]["mensaje"].lower()

    # 4. Rechazo con motivo fundado debe prosperar
    resp_ok = await client.post(
        f"/pedidos/{pedido_id}/rechazar",
        json={"motivo": "Solicitud no corresponde a actividades curriculares aprobadas."},
        headers=auth_admin,
    )
    assert resp_ok.status_code == 200
    assert resp_ok.json()["estado"] == EstadoPedido.RECHAZADO.value


async def test_escenario_5_abm_templates_y_limite_constitucional(client, auth_admin):
    """Escenario 5: ABM de templates y validación del límite de 8 GB sin justificación."""
    # 1. Crear template con 10 GB de disco sin justificación debe fallar 400
    resp_sin_just = await client.post(
        "/templates/",
        json={
            "nombre": "Template Excesivo Sin Justificar",
            "modelo_servicio": "iaas",
            "tipo": "lxc",
            "default_disk_gb": 10,
        },
        headers=auth_admin,
    )
    assert resp_sin_just.status_code == 400
    assert "8 GB" in resp_sin_just.json()["detail"]["mensaje"]

    # 2. Con justificación debe tener éxito
    resp_con_just = await client.post(
        "/templates/",
        json={
            "nombre": "Template Con Justificación Valida",
            "modelo_servicio": "iaas",
            "tipo": "lxc",
            "default_disk_gb": 10,
            "justificacion_disco": "Requerido para imágenes ISO de laboratorio",
        },
        headers=auth_admin,
    )
    assert resp_con_just.status_code == 201
    template_id = resp_con_just.json()["id"]

    # 3. Baja lógica / Soft delete del template
    resp_del = await client.delete(f"/templates/{template_id}", headers=auth_admin)
    assert resp_del.status_code == 200
    assert resp_del.json()["activo"] is False


async def test_escenario_6_autogestion_reinicio_y_metricas(client, auth_catedra, catedra, template, db, proxmox):
    """Escenario 6: Autogestión de servicios (reinicio y métricas en tiempo real)."""
    # 1. Crear servicio existente para la cátedra
    servicio = await factories.crear_servicio(
        db,
        catedra_id=catedra.id,
        template_id=template.id,
        proxmox_vmid="101",
        estado=EstadoServicio.RUNNING,
    )
    proxmox.estados[101] = "running"

    # 2. Reiniciar el servicio
    resp_reboot = await client.post(f"/servicios/{servicio.id}/reboot", headers=auth_catedra)
    assert resp_reboot.status_code == 200
    assert resp_reboot.json()["estado"] == EstadoServicio.RUNNING.value

    # 3. Consultar métricas del servicio
    resp_metricas = await client.get(f"/servicios/{servicio.id}/metricas", headers=auth_catedra)
    assert resp_metricas.status_code == 200
    m_data = resp_metricas.json()
    assert "cpu_usage_percent" in m_data
    assert "ram_usage_mb" in m_data
