"""Validación End-to-End de los 6 escenarios de quickstart.md."""

from datetime import timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.pedido import EstadoPedido, ModeloServicio, Pedido
from app.models.servicio import EstadoServicio
from app.utils.clock import clock
from app.worker import procesar_una
from tests import factories
from tests.capacity_helpers import aprobar_http, materializado, perfil_capacidad, seleccion  # noqa: F401
from tests.service_helpers import link_capacity_definition
from tests.test_operaciones_recuperacion import prepared_guest  # noqa: F401


@pytest.fixture(autouse=True)
def cluster(proxmox, perfil_capacidad):
    return proxmox


def _vigencia_activa():
    today = clock.now().astimezone(ZoneInfo("America/Argentina/Tucuman")).date()
    return {
        "tipo": "personalizado",
        "desde": today.isoformat(),
        "hasta": (today + timedelta(days=30)).isoformat(),
    }


async def test_escenario_1_flujo_principal_iaas(
    client, engine, db, auth_admin, auth_catedra, catedra, template, proxmox, prepared_guest
):
    """Escenario 1: Solicitud IaaS, evaluación y despliegue automático exitoso."""
    # 1. Docente envía solicitud IaaS
    resp_pedido = await client.post(
        "/pedidos/",
        json={
            "template_id": template.id,
            "modelo_servicio": "iaas",
            "descripcion_requerimientos": "Entorno de laboratorio básico Linux",
            "vigencia": _vigencia_activa(),
            "catedra_id": catedra.id,
        },
        headers=auth_catedra | {"Idempotency-Key": f"ped-{uuid4()}"},
    )
    assert resp_pedido.status_code == 201, resp_pedido.text
    pedido_data = resp_pedido.json()
    assert pedido_data["estado"] == EstadoPedido.SOLICITADO.value
    pedido_id = pedido_data["id"]

    # 2. Administrador consulta pedidos solicitados
    resp_listar = await client.get("/pedidos/?estado=solicitado", headers=auth_admin)
    assert resp_listar.status_code == 200
    ids = [p["id"] for p in resp_listar.json()]
    assert pedido_id in ids

    # 3. Administrador aprueba con despliegue inmediato y el worker ejecuta la operación
    pedido = await db.get(Pedido, pedido_id)
    resp_aprobar = await aprobar_http(
        client,
        pedido,
        template,
        auth_admin,
        clave=f"apr-{uuid4()}",
        desplegar_inmediatamente=True,
    )
    assert resp_aprobar.status_code == 202, resp_aprobar.text

    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await procesar_una(sessions, pve=proxmox)
    db.expire_all()

    # 4. Docente consulta sus servicios y verifica el aprovisionamiento
    resp_servicios = await client.get("/servicios/", headers=auth_catedra)
    assert resp_servicios.status_code == 200
    servicios = resp_servicios.json()
    assert any(s["pedido_id"] == pedido_id for s in servicios)


async def test_escenario_2_saas_paas_opciones_avanzadas(
    client, engine, db, admin, auth_admin, auth_catedra, catedra, proxmox, prepared_guest, monkeypatch
):
    """Escenario 2: Solicitud SaaS con perfil publicado y entrega separada de acceso."""
    template_saas = await factories.crear_template(
        db, nombre="BookStack SaaS", modelo_servicio=ModeloServicio.SAAS
    )
    await link_capacity_definition(db, template_saas, admin, product="bookstack")
    from app.config import get_settings
    from app.services import bootstrap_service
    monkeypatch.setattr(get_settings(), 'network_profiles', {'test-network':{
        'bridge':'vmbr0','nodes':['pve1'],'allowed_cidrs':['10.20.0.0/24'],'client_cidrs':['10.30.0.0/24'],
        'instances':{str(uuid4()):{'host':'libros-test.example.edu','address':'10.20.0.10',
            'mac_address':'02:00:00:00:00:10','products':['bookstack']}}}})
    async def prepared_network(**kwargs):
        return {'net0':'name=eth0,bridge=vmbr0,ip=dhcp','network_profile_id':'test-network'}
    monkeypatch.setattr(bootstrap_service,'validar_preparacion',prepared_network)
    proxmox.contenidos_storage[("pve1", "local")].append(
        {"volid": "local:vztmpl/bookstack-test.tar.zst", "content": "vztmpl", "size": 1024**3}
    )

    # 1. Docente pide servicio SaaS
    resp_pedido = await client.post(
        "/pedidos/",
        json={
            "template_id": template_saas.id,
            "modelo_servicio": "saas",
            "descripcion_requerimientos": "Libro virtual interactivo para cátedra de Sistemas Operativos",
            "vigencia": _vigencia_activa(),
            "catedra_id": catedra.id,
        },
        headers=auth_catedra | {"Idempotency-Key": f"ped-{uuid4()}"},
    )
    assert resp_pedido.status_code == 201, resp_pedido.text
    pedido_id = resp_pedido.json()["id"]

    # 2. Administrador aprueba seleccionando perfil y destino validados
    pedido = await db.get(Pedido, pedido_id)
    resp_aprobar = await aprobar_http(
        client,
        pedido,
        template_saas,
        auth_admin,
        clave=f"apr-{uuid4()}",
        desplegar_inmediatamente=True,
    )
    assert resp_aprobar.status_code == 202, resp_aprobar.text

    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await procesar_una(sessions, pve=proxmox)
    db.expire_all()

    # 3. Comprobar que el servicio está materializado y expone su estado de acceso separado
    await db.refresh(pedido)
    servicio_id = pedido.servicio_id
    assert servicio_id is not None
    resp_serv = await client.get(f"/servicios/{servicio_id}", headers=auth_catedra)
    assert resp_serv.status_code == 200
    s_data = resp_serv.json()
    assert s_data["disponibilidad_aplicacion"] == "no_verificada"
    assert "credenciales_acceso" not in s_data


async def test_escenario_3_negociacion_y_ajuste(client, auth_admin, auth_catedra, catedra, template):
    """Escenario 3: Ciclo de ajuste colaborativo (solicitar-ajuste y reenviar)."""
    # 1. Docente envía pedido
    resp = await client.post(
        "/pedidos/",
        json={
            "template_id": template.id,
            "modelo_servicio": "iaas",
            "descripcion_requerimientos": "Servidor con 64GB de RAM",
            "vigencia": _vigencia_activa(),
            "catedra_id": catedra.id,
        },
        headers=auth_catedra | {"Idempotency-Key": f"ped-{uuid4()}"},
    )
    assert resp.status_code == 201, resp.text
    pedido_id = resp.json()["id"]

    # 2. Administrador solicita ajuste
    resp_ajuste = await client.post(
        f"/pedidos/{pedido_id}/solicitar-ajuste",
        json={"observaciones": "Capacidad reducida en memoria RAM; se sugiere ajustar a 4GB."},
        headers=auth_admin | {"Idempotency-Key": f"aj-{uuid4()}"},
    )
    assert resp_ajuste.status_code == 200, resp_ajuste.text
    assert resp_ajuste.json()["estado"] == EstadoPedido.REQUIERE_AJUSTE.value

    # 3. Se reenvía el pedido ajustado
    resp_reenviar = await client.post(
        f"/pedidos/{pedido_id}/reenviar",
        json={
            "descripcion_requerimientos": "Ajustado a 4GB de RAM conforme a lo sugerido",
            "vigencia": _vigencia_activa(),
        },
        headers=auth_admin | {"Idempotency-Key": f"re-{uuid4()}"},
    )
    assert resp_reenviar.status_code == 200, resp_reenviar.text
    assert resp_reenviar.json()["estado"] == EstadoPedido.SOLICITADO.value


async def test_escenario_4_rechazo_fundado_obligatorio(client, auth_admin, auth_catedra, catedra, template):
    """Escenario 4: Rechazo requiere justificación escrita obligatoria."""
    # 1. Docente envía pedido
    resp = await client.post(
        "/pedidos/",
        json={
            "template_id": template.id,
            "modelo_servicio": "iaas",
            "vigencia": _vigencia_activa(),
            "catedra_id": catedra.id,
        },
        headers=auth_catedra | {"Idempotency-Key": f"ped-{uuid4()}"},
    )
    assert resp.status_code == 201, resp.text
    pedido_id = resp.json()["id"]

    # 2. Rechazo con cuerpo vacío debe fallar 422
    resp_vacio = await client.post(
        f"/pedidos/{pedido_id}/rechazar",
        json={},
        headers=auth_admin | {"Idempotency-Key": f"rej1-{uuid4()}"},
    )
    assert resp_vacio.status_code == 422

    # 3. Rechazo con motivo solo espacios debe fallar 422
    resp_espacios = await client.post(
        f"/pedidos/{pedido_id}/rechazar",
        json={"motivo": "    "},
        headers=auth_admin | {"Idempotency-Key": f"rej2-{uuid4()}"},
    )
    assert resp_espacios.status_code in {400, 422}
    assert "motivo" in resp_espacios.json()["detail"]["mensaje"].lower()

    # 4. Rechazo con motivo fundado debe prosperar
    resp_ok = await client.post(
        f"/pedidos/{pedido_id}/rechazar",
        json={"motivo": "Solicitud no corresponde a actividades curriculares aprobadas."},
        headers=auth_admin | {"Idempotency-Key": f"rej3-{uuid4()}"},
    )
    assert resp_ok.status_code == 200, resp_ok.text
    assert resp_ok.json()["estado"] == EstadoPedido.RECHAZADO.value


async def test_escenario_5_abm_templates_y_limite_constitucional(client, auth_admin, template):
    """Escenario 5: ABM de templates con definición publicada y disco grande sin tope artificial."""
    # 1. Crear template sin definición publicada debe fallar 422
    resp_sin_def = await client.post(
        "/templates/",
        json={
            "nombre": "Template Sin Definicion",
            "modelo_servicio": "iaas",
            "tipo": "lxc",
            "default_disk_gb": 16,
        },
        headers=auth_admin,
    )
    assert resp_sin_def.status_code == 422
    assert resp_sin_def.json()["detail"]["codigo"] in {"definicion_requerida", "datos_invalidos"}

    # 2. Con definición publicada y disco grande (16 GB) se acepta sin restricción
    resp_con_def = await client.post(
        "/templates/",
        json={
            "nombre": "Template Disco Grande Validado",
            "modelo_servicio": "iaas",
            "tipo": "lxc",
            "default_vcpus": 2,
            "default_ram_mb": 2048,
            "default_disk_gb": 16,
            "definicion_version_id": str(template.definicion_version_id),
        },
        headers=auth_admin,
    )
    assert resp_con_def.status_code == 201, resp_con_def.text
    assert resp_con_def.json()["default_disk_gb"] == 16
    template_id = resp_con_def.json()["id"]

    # 3. Baja lógica / Soft delete del template
    resp_del = await client.delete(f"/templates/{template_id}", headers=auth_admin)
    assert resp_del.status_code == 200
    assert resp_del.json()["activo"] is False


async def test_escenario_6_autogestion_reinicio_y_metricas(
    client, engine, auth_catedra, catedra, usuario_catedra, template, db, proxmox
):
    """Escenario 6: Autogestión de servicios (reinicio y métricas en tiempo real)."""
    servicio, ledger = await materializado(
        db, proxmox, catedra, usuario_catedra, template, vmid=101
    )
    servicio.estado = EstadoServicio.RUNNING
    ledger.vcpus_retenidos = servicio.vcpus_asignados
    ledger.ram_mb_retenida = servicio.ram_asignada_mb
    proxmox.estados[101] = "running"
    for r in proxmox.recursos:
        if int(r["vmid"]) == 101:
            r["status"] = "running"
    await db.commit()

    # 2. Reiniciar el servicio
    resp_reboot = await client.post(
        f"/servicios/{servicio.id}/reboot",
        headers=auth_catedra | {"Idempotency-Key": f"reb-{uuid4()}"},
        json={},
    )
    assert resp_reboot.status_code == 202, resp_reboot.text
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await procesar_una(sessions, pve=proxmox)
    await db.refresh(servicio)
    assert servicio.estado == EstadoServicio.RUNNING

    # 3. Consultar métricas del servicio
    resp_metricas = await client.get(f"/servicios/{servicio.id}/metricas", headers=auth_catedra)
    assert resp_metricas.status_code == 200
    m_data = resp_metricas.json()
    assert "cpu_usage_percent" in m_data
    assert "ram_usage_mb" in m_data
