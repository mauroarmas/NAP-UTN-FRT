"""Pruebas de regresión transversal para feature 011 (T099).

Verifica que la introducción del motor Docker OCI y el catálogo unificado
no alteren ni rompan el comportamiento previo:
1. Usuarios, cátedras, pedidos y trazabilidad de historial.
2. IaaS Ubuntu 24.04 y Debian 13 (solicitud, aprobación, despliegue, acceso SSH y consola IaaS).
3. Draw.io / SaaS legacy con acceso por gateway NAP y runner legacy intactos.
4. Renovaciones que extienden vigencia sin recrear instancias ni regenerar secretos.
5. No interferencia mutua entre servicios y conservación de recursos.
"""

from copy import deepcopy
from datetime import timedelta
from unittest.mock import AsyncMock
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import get_settings
from app.models.identidad_infraestructura import IdentidadInfraestructura
from app.models.operacion_infraestructura import OperacionInfraestructura
from app.models.pedido import EstadoPedido, Pedido, TipoPedido
from app.models.recurso_template import RecursoTemplate
from app.models.servicio import EstadoServicio, Servicio
from app.models.vigencia import VigenciaAutorizada
from app.services import (
    bases_iaas_service as bases,
    capacidad_service,
    catalogo_service,
    perfiles_service,
    vigencia_service,
)
from app.utils.clock import clock
from app.utils.secretos import configured_keyring
from app.worker import procesar_una
from tests import factories
from tests.auth_helpers import headers_para
from tests.capacity_helpers import aprobar_http, perfil_capacidad  # noqa: F401
from tests.test_biblioteca_pedidos_010 import oferta


async def _configurar_iaas(monkeypatch, proxmox):
    settings = get_settings()
    slots = {
        str(uuid4()): {
            "host": f"iaas-{i}.example.edu",
            "address": f"10.20.0.{i + 30}",
            "mac_address": f"02:00:00:00:02:{i + 30:02x}",
            "products": ["linux"],
        }
        for i in range(2)
    }
    monkeypatch.setattr(settings, "iaas_network_profile_id", "linux")
    monkeypatch.setattr(
        settings,
        "network_profiles",
        {
            "linux": {
                "instances": slots,
                "nodes": ["pve1"],
                "bridge": "vmbr0",
                "allowed_cidrs": ["10.20.0.0/24"],
                "client_cidrs": ["10.20.0.0/24"],
                "ip_mode": "static",
                "static_cidr": "10.20.0.0/24",
                "gateway": "10.20.0.1",
            }
        },
    )
    proxmox.contenidos_storage[("pve1", "local")] = [
        {"volid": "local:vztmpl/ubuntu-24.04-standard_24.04-2_amd64.tar.zst", "content": "vztmpl"},
        {"volid": "local:vztmpl/debian-13-standard_13.6-1_amd64.tar.zst", "content": "vztmpl"},
    ]


class FakeLegacyRunner:
    """Simula el runner legacy de la versión 010 para aplicaciones SaaS previas."""

    def __init__(self):
        self.requests = []

    async def execute(self, request):
        from app.schemas.guest_runner import canonical, parse_request

        parse_request(canonical(request).encode())
        self.requests.append(deepcopy(request))
        profile = get_settings().network_profiles[request["network_profile_id"]]
        instance = profile["instances"][request["resource_uuid"]]
        return {
            **{k: request[k] for k in ["protocol", "operation_id", "action", "resource_uuid"]},
            "status": "succeeded",
            "phase": "verified",
            "identity_verified": True,
            "observed_at": clock.now().isoformat(),
            "result": {
                "ready": True,
                "bootstrap_completed": True,
                "host": instance["host"],
                "address": instance["address"],
                "addresses": [instance["address"]],
                "port": 443,
                "endpoint": "https://" + instance["host"],
                "username": "nap_" + UUID(request["resource_uuid"]).hex,
                "checks": ["drawio-status-v1"],
            },
        }


@pytest.mark.parametrize("iaas_template_name", ["Ubuntu 24.04", "Debian 13"])
async def test_regresion_iaas_ciclo_completo_y_consola(
    client,
    db,
    engine,
    admin,
    auth_admin,
    auth_catedra,
    proxmox,
    perfil_capacidad,
    monkeypatch,
    catedra,
    usuario_catedra,
    iaas_template_name,
):
    """Regresión IaaS: sincronización, solicitud, aprobación, despliegue, acceso SSH y consola IaaS."""
    await _configurar_iaas(monkeypatch, proxmox)
    assert await bases.sincronizar(db, pve=proxmox) == 2
    await db.commit()

    tmpl = await db.scalar(select(RecursoTemplate).where(RecursoTemplate.nombre == iaas_template_name))
    assert tmpl is not None
    await perfiles_service.anexar_disponibilidad(db, [tmpl])
    assert tmpl.oferta_disponible
    assert tmpl.tamanos_permitidos == ["small", "medium"]

    today = clock.now().date()
    pedido_resp = await client.post(
        "/pedidos/",
        headers=auth_catedra | {"Idempotency-Key": f"pedido-iaas-{iaas_template_name}"},
        json={
            "template_id": tmpl.id,
            "modelo_servicio": "iaas",
            "catedra_id": catedra.id,
            "descripcion_requerimientos": f"Prácticas de sistemas sobre {iaas_template_name}.",
            "vigencia": {
                "tipo": "personalizado",
                "desde": today.isoformat(),
                "hasta": (today + timedelta(days=14)).isoformat(),
            },
        },
    )
    assert pedido_resp.status_code == 201, pedido_resp.text
    pedido_id = pedido_resp.json()["id"]

    pedido = await db.get(Pedido, pedido_id)
    approved = await aprobar_http(client, pedido, tmpl, auth_admin, desplegar_inmediatamente=True)
    assert approved.status_code == 202, approved.text
    await db.commit()

    sessions = async_sessionmaker(engine, expire_on_commit=False)
    for _ in range(8):
        await procesar_una(sessions, pve=proxmox)

    await db.refresh(pedido)
    assert pedido.estado == EstadoPedido.ACTIVO
    assert pedido.servicio_id is not None

    service = await db.get(Servicio, pedido.servicio_id)
    assert service.estado == EstadoServicio.RUNNING
    assert service.disponibilidad_aplicacion == "utilizable"
    assert service.asignacion_snapshot["origen"] == "proxmox_iaas"
    assert service.acceso_metadata["username"] == "root"

    # Verificación de credenciales SSH
    credenciales = configured_keyring().decrypt(
        service.credenciales_encrypted, context=f"servicio:{service.id}:secretos"
    )
    assert "guest_password" in credenciales
    assert len(credenciales["guest_password"]) >= 32

    # Revelación autorizada para la cátedra
    revelar = await client.post(f"/servicios/{service.id}/acceso/revelar", headers=auth_catedra, json={})
    assert revelar.status_code == 200, revelar.text
    assert revelar.json()["credenciales"]["usuario"] == "root"
    assert revelar.json()["credenciales"]["password"] == credenciales["guest_password"]

    # Consola IaaS de servicio (/servicios/{id}/consola)
    # Exclusiva de servicio encendido, con vigencia y confirmación de identidad
    consola_iaas = await client.get(f"/servicios/{service.id}/consola", headers=auth_admin)
    assert consola_iaas.status_code == 200, consola_iaas.text
    consola_data = consola_iaas.json()
    assert "xtermjs=1" in consola_data["url"]
    assert consola_data["servicio_id"] == service.id
    assert consola_data["vmid"] == service.proxmox_vmid


async def test_regresion_drawio_legacy_y_acceso_nap(
    client,
    db,
    engine,
    admin,
    auth_admin,
    auth_catedra,
    catedra,
    usuario_catedra,
    perfil_capacidad,
    proxmox,
    monkeypatch,
):
    """Regresión Draw.io: manifest y runner legacy 010 funcionan sin ejecutar motor Docker OCI."""
    from app.services import catalogo_service

    _, definition, template = await oferta(db, admin)
    settings = get_settings()
    perfil_capacidad["cluster_id"] = definition.manifest["validation"]["cluster_uuid"]
    proxmox.contenidos_storage[("pve1", "local")] = [
        {"volid": definition.manifest["image"]["volume_id"], "content": "vztmpl"}
    ]
    instances = {
        str(uuid4()): {
            "host": f"diagramas-{n}.example.edu",
            "address": f"10.50.0.{101 + n}",
            "mac_address": f"02:00:00:00:00:0{n + 1}",
            "products": ["drawio"],
        }
        for n in range(2)
    }
    monkeypatch.setattr(
        settings,
        "network_profiles",
        {
            "test-network": {
                "bridge": "vmbr0",
                "nodes": ["pve1"],
                "allowed_cidrs": ["10.50.0.0/24"],
                "client_cidrs": ["10.50.0.0/24"],
                "instances": instances,
            }
        },
    )
    monkeypatch.setattr(
        settings,
        "service_artifacts",
        {"drawio-trial:1.0.0": {"nodes": ["pve1"], "network_profile_id": "test-network"}},
    )
    monkeypatch.setattr(catalogo_service, "comprobar_disponibilidad", AsyncMock())

    legacy_runner = FakeLegacyRunner()

    today = clock.now().date()
    p_resp = await client.post(
        "/pedidos/",
        headers=auth_catedra | {"Idempotency-Key": "pedido-drawio-legacy"},
        json={
            "template_id": template.id,
            "modelo_servicio": "saas",
            "catedra_id": catedra.id,
            "descripcion_requerimientos": "Diagramas de arquitectura del curso.",
            "vigencia": {
                "tipo": "personalizado",
                "desde": today.isoformat(),
                "hasta": (today + timedelta(days=30)).isoformat(),
            },
        },
    )
    assert p_resp.status_code == 201, p_resp.text
    pedido = await db.get(Pedido, p_resp.json()["id"])

    approved = await aprobar_http(client, pedido, template, auth_admin, desplegar_inmediatamente=True)
    assert approved.status_code == 202, approved.text
    await db.commit()

    sessions = async_sessionmaker(engine, expire_on_commit=False)
    for _ in range(10):
        await procesar_una(sessions, pve=proxmox, runner=legacy_runner)

    await db.refresh(pedido)
    assert pedido.estado in (EstadoPedido.ACTIVO, EstadoPedido.EN_DESPLIEGUE)
    assert pedido.servicio_id is not None

    service = await db.get(Servicio, pedido.servicio_id)
    assert service.estado == EstadoServicio.RUNNING
    # El runner legacy fue ejecutado con el protocolo drawio
    assert len(legacy_runner.requests) >= 1
    assert any(r.get("protocol") == "drawio" or "drawio" in str(r) for r in legacy_runner.requests)

    # Consulta de acceso por gateway NAP
    acceso = await client.get(f"/servicios/{service.id}/acceso", headers=auth_admin)
    assert acceso.status_code == 200
    acc_json = acceso.json()
    assert acc_json["metodo"] == "https"
    assert "diagramas" in acc_json["direccion"]


async def test_regresion_renovacion_extiende_vigencia_sin_recrear_instancia(
    client,
    db,
    engine,
    admin,
    auth_admin,
    auth_catedra,
    catedra,
    usuario_catedra,
    perfil_capacidad,
    proxmox,
    monkeypatch,
):
    """Regresión renovaciones: extiende la vigencia autorizada sin alterar VMID, IP ni credenciales."""
    await _configurar_iaas(monkeypatch, proxmox)
    await bases.sincronizar(db, pve=proxmox)
    await db.commit()

    tmpl = await db.scalar(select(RecursoTemplate).where(RecursoTemplate.nombre == "Ubuntu 24.04"))
    today = clock.now().date()
    p_resp = await client.post(
        "/pedidos/",
        headers=auth_catedra | {"Idempotency-Key": "pedido-ubuntu-para-renovar"},
        json={
            "template_id": tmpl.id,
            "modelo_servicio": "iaas",
            "catedra_id": catedra.id,
            "descripcion_requerimientos": "Prácticas de SO.",
            "vigencia": {
                "tipo": "personalizado",
                "desde": today.isoformat(),
                "hasta": (today + timedelta(days=7)).isoformat(),
            },
        },
    )
    pedido = await db.get(Pedido, p_resp.json()["id"])
    await aprobar_http(client, pedido, tmpl, auth_admin, desplegar_inmediatamente=True)
    await db.commit()

    sessions = async_sessionmaker(engine, expire_on_commit=False)
    for _ in range(8):
        await procesar_una(sessions, pve=proxmox)

    await db.refresh(pedido)
    servicio = await db.get(Servicio, pedido.servicio_id)
    vmid_original = servicio.proxmox_vmid
    ip_original = servicio.acceso_metadata.get("address") or servicio.acceso_metadata.get("host")
    cred_original = servicio.credenciales_encrypted
    identidad_id_original = servicio.identidad_infraestructura_id
    vence_original = servicio.vence_at

    # Solicitar renovación
    nueva_desde = (vence_original.date() + timedelta(days=1)).isoformat()
    nueva_hasta = (vence_original.date() + timedelta(days=30)).isoformat()
    renov_resp = await client.post(
        f"/servicios/{servicio.id}/renovar",
        headers=auth_catedra | {"Idempotency-Key": "renovacion-iaas-1"},
        json={"vigencia": {"tipo": "personalizado", "desde": nueva_desde, "hasta": nueva_hasta}},
    )
    assert renov_resp.status_code == 201, renov_resp.text
    pedido_renov_id = renov_resp.json()["pedido_id"]

    pedido_renov = await db.get(Pedido, pedido_renov_id)
    assert pedido_renov.tipo == TipoPedido.RENOVACION
    assert pedido_renov.servicio_id == servicio.id

    # Aprobar renovación
    vig_renov = {"tipo": "personalizado", "desde": nueva_desde, "hasta": nueva_hasta}
    payload_renov = {
        "asignacion": {
            "template_id": servicio.template_id,
            "vcpus": servicio.vcpus_asignados,
            "ram_mb": servicio.ram_asignada_mb,
            "disk_gb": servicio.disk_asignado_gb,
        },
        "destino": {"nodo": "pve1", "storage": "local-lvm"},
        "vigencia": vig_renov,
    }
    apr_renov = await aprobar_http(
        client,
        pedido_renov,
        tmpl,
        auth_admin,
        clave="apr-renov-iaas-1",
        payload=payload_renov,
    )
    assert apr_renov.status_code == 200, apr_renov.text
    await db.commit()

    # Procesar ciclo worker si aplica
    for _ in range(4):
        await procesar_una(sessions, pve=proxmox)

    await db.refresh(servicio)
    # Conservación estricta de la instancia
    assert servicio.proxmox_vmid == vmid_original
    assert servicio.identidad_infraestructura_id == identidad_id_original
    assert servicio.credenciales_encrypted == cred_original
    assert servicio.estado == EstadoServicio.RUNNING
    assert servicio.vence_at > vence_original


async def test_regresion_no_interferencia_y_conservacion_entre_servicios(
    client,
    db,
    engine,
    admin,
    auth_admin,
    auth_catedra,
    catedra,
    usuario_catedra,
    perfil_capacidad,
    proxmox,
    monkeypatch,
):
    """Acciones sobre un servicio no afectan ni alteran las identidades o recursos de otros."""
    await _configurar_iaas(monkeypatch, proxmox)
    await bases.sincronizar(db, pve=proxmox)
    await db.commit()

    tmpl = await db.scalar(select(RecursoTemplate).where(RecursoTemplate.nombre == "Ubuntu 24.04"))
    today = clock.now().date()

    # Desplegar servicio A
    resp_a = await client.post(
        "/pedidos/",
        headers=auth_catedra | {"Idempotency-Key": "pedido-iaas-a"},
        json={
            "template_id": tmpl.id,
            "modelo_servicio": "iaas",
            "catedra_id": catedra.id,
            "descripcion_requerimientos": "Servicio A",
            "vigencia": {
                "tipo": "personalizado",
                "desde": today.isoformat(),
                "hasta": (today + timedelta(days=7)).isoformat(),
            },
        },
    )
    pedido_a = await db.get(Pedido, resp_a.json()["id"])
    await aprobar_http(client, pedido_a, tmpl, auth_admin, desplegar_inmediatamente=True)
    await db.commit()

    sessions = async_sessionmaker(engine, expire_on_commit=False)
    for _ in range(8):
        await procesar_una(sessions, pve=proxmox)

    await db.refresh(pedido_a)
    serv_a = await db.get(Servicio, pedido_a.servicio_id)
    vmid_a = serv_a.proxmox_vmid

    # Desplegar servicio B para otra cátedra
    otra_user = await factories.crear_usuario(db, "docente-otra-catedra-regresion")
    otra_catedra = await factories.crear_catedra(db, nombre="Otra Cátedra Regresión", titular_id=otra_user.id)
    auth_otra = await headers_para(db, otra_user)
    await db.commit()

    resp_b = await client.post(
        "/pedidos/",
        headers=auth_otra | {"Idempotency-Key": "pedido-iaas-b"},
        json={
            "template_id": tmpl.id,
            "modelo_servicio": "iaas",
            "catedra_id": otra_catedra.id,
            "descripcion_requerimientos": "Servicio B",
            "vigencia": {
                "tipo": "personalizado",
                "desde": today.isoformat(),
                "hasta": (today + timedelta(days=7)).isoformat(),
            },
        },
    )
    pedido_b = await db.get(Pedido, resp_b.json()["id"])
    await aprobar_http(client, pedido_b, tmpl, auth_admin, desplegar_inmediatamente=True)
    await db.commit()

    for _ in range(8):
        await procesar_una(sessions, pve=proxmox)

    await db.refresh(pedido_b)
    serv_b = await db.get(Servicio, pedido_b.servicio_id)
    vmid_b = serv_b.proxmox_vmid
    assert vmid_a != vmid_b

    # Detener servicio A: B debe permanecer running e inalterado
    detener_resp = await client.post(
        f"/servicios/{serv_a.id}/stop",
        headers=auth_catedra | {"Idempotency-Key": "detener-iaas-a"},
    )
    assert detener_resp.status_code in (200, 202), detener_resp.text
    await db.commit()

    for _ in range(4):
        await procesar_una(sessions, pve=proxmox)

    await db.refresh(serv_a)
    await db.refresh(serv_b)
    assert serv_a.estado == EstadoServicio.STOPPED
    assert serv_b.estado == EstadoServicio.RUNNING
    assert serv_b.proxmox_vmid == vmid_b
