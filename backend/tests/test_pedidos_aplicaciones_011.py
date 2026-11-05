"""Pruebas de solicitudes de aplicaciones (US3 - T065):
Otro con imagen opcional sin credenciales, pertenencia de cátedra,
aclaración/rechazo/reenvío, revisión congelada y valores sensibles write-only.
"""
from copy import deepcopy
from datetime import timedelta
import pytest
from sqlalchemy import select, func
from zoneinfo import ZoneInfo

from app.models.pedido import Pedido, EstadoPedido, ModeloServicio
from app.models.compromiso_capacidad import CompromisoCapacidad
from app.models.secreto_despliegue import SecretoDespliegue
from app.models.decision_idempotente import DecisionIdempotente
from app.utils.clock import clock
from tests import factories
from tests.capacity_helpers import perfil_capacidad, seleccion
from tests.test_reserva_red_aplicacion_011 import red_aplicaciones_011
from infra.applications.tests.conftest import profile_entry
from tests.test_admision_aplicaciones_011 import app_order, approve


def _vigencia():
    hoy = clock.now().astimezone(ZoneInfo("America/Argentina/Tucuman")).date()
    return {
        "tipo": "personalizado",
        "desde": hoy.isoformat(),
        "hasta": (hoy + timedelta(days=60)).isoformat(),
    }


async def test_docente_puede_solicitar_otro_con_referencia_e_instrucciones_sin_reserva(
    client, db, auth_catedra, catedra, proxmox
):
    payload = {
        "catedra_id": catedra.id,
        "template_id": None,
        "modelo_servicio": "saas",
        "descripcion_requerimientos": "Prácticas de laboratorio con software de simulación específico",
        "vigencia": _vigencia(),
        "parametros_extra": {
            "titulo": "Simulador de Circuitos",
            "software_solicitado": "CircuitsApp",
            "referencia_imagen": "universidad/circuits:2.4.0",
            "instrucciones_uso": "Expone puerto web 8080. Requiere 1 GB de RAM.",
        },
    }
    response = await client.post(
        "/pedidos/",
        json=payload,
        headers=auth_catedra | {"Idempotency-Key": "otro-con-imagen-1"},
    )
    assert response.status_code == 201, response.text
    pedido_id = response.json()["id"]

    pedido = await db.get(Pedido, pedido_id)
    assert pedido is not None
    assert pedido.estado == EstadoPedido.SOLICITADO
    assert pedido.parametros_extra["referencia_imagen"] == "universidad/circuits:2.4.0"
    assert pedido.parametros_extra["instrucciones_uso"] == "Expone puerto web 8080. Requiere 1 GB de RAM."
    assert pedido.parametros_extra["software_solicitado"] == "CircuitsApp"

    # No reserva capacidad ni crea contenedores
    assert await db.scalar(select(func.count()).select_from(CompromisoCapacidad)) == 0
    assert len(proxmox.creados) == 0


@pytest.mark.parametrize(
    "bad_ref",
    [
        "http://user:pass@registry.example.com/app:1.0",
        "https://admin:secret@hub.docker.com/r/myorg/app",
        "user:password@registry.example.com/image",
        "myorg/app:1.0 with spaces",
    ],
)
async def test_referencia_con_credenciales_o_formato_invalido_es_rechazada(
    client, auth_catedra, catedra, bad_ref
):
    payload = {
        "catedra_id": catedra.id,
        "template_id": None,
        "modelo_servicio": "saas",
        "descripcion_requerimientos": "Uso académico para laboratorio",
        "vigencia": _vigencia(),
        "parametros_extra": {
            "titulo": "Software con credenciales",
            "software_solicitado": "App Secreta",
            "referencia_imagen": bad_ref,
        },
    }
    response = await client.post(
        "/pedidos/",
        json=payload,
        headers=auth_catedra | {"Idempotency-Key": f"bad-ref-{hash(bad_ref)}"},
    )
    assert response.status_code == 422


async def test_solicitud_para_otra_catedra_es_rechazada(
    client, db, auth_catedra
):
    otra_catedra = await factories.crear_catedra(db, nombre="Otra Cátedra No Vinculada")
    await db.commit()

    payload = {
        "catedra_id": otra_catedra.id,
        "template_id": None,
        "modelo_servicio": "saas",
        "descripcion_requerimientos": "Intento no autorizado",
        "vigencia": _vigencia(),
        "parametros_extra": {
            "titulo": "Intento de otra cátedra",
            "software_solicitado": "App",
        },
    }
    response = await client.post(
        "/pedidos/",
        json=payload,
        headers=auth_catedra | {"Idempotency-Key": "otra-catedra-1"},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["codigo"] == "sin_permisos"


async def test_flujo_aclaracion_rechazo_y_reenvio_sin_reservas_prematuras(
    client, db, auth_catedra, auth_admin, catedra, proxmox
):
    # 1. Crear solicitud
    payload = {
        "catedra_id": catedra.id,
        "template_id": None,
        "modelo_servicio": "saas",
        "descripcion_requerimientos": "Laboratorio inicial",
        "vigencia": _vigencia(),
        "parametros_extra": {
            "titulo": "App para aclarar",
            "software_solicitado": "App Base",
            "referencia_imagen": "org/app:v1",
        },
    }
    res = await client.post(
        "/pedidos/",
        json=payload,
        headers=auth_catedra | {"Idempotency-Key": "aclaracion-crear"},
    )
    assert res.status_code == 201
    pedido_id = res.json()["id"]

    # 2. Admin solicita ajuste/aclaración
    res_ajuste = await client.post(
        f"/pedidos/{pedido_id}/aclaracion",
        json={"observaciones": "Indicar qué puertos requiere y cantidad esperada de alumnos."},
        headers=auth_admin | {"Idempotency-Key": "aclaracion-pedir"},
    )
    assert res_ajuste.status_code == 200
    pedido = await db.get(Pedido, pedido_id)
    assert pedido.estado == EstadoPedido.REQUIERE_AJUSTE
    assert await db.scalar(select(func.count()).select_from(CompromisoCapacidad)) == 0

    # 3. Docente reenvía corregido
    res_reenviar = await client.post(
        f"/pedidos/{pedido_id}/reenviar",
        json={
            "vigencia": _vigencia(),
            "descripcion_requerimientos": "Laboratorio ampliado para 50 alumnos simultáneos.",
            "parametros_extra": {
                "titulo": "App para aclarar corregida",
                "software_solicitado": "App Base",
                "referencia_imagen": "org/app:v1.1",
                "instrucciones_uso": "Puerto web 3000.",
            },
        },
        headers=auth_catedra | {"Idempotency-Key": "aclaracion-reenviar"},
    )
    assert res_reenviar.status_code == 200
    await db.refresh(pedido)
    assert pedido.estado == EstadoPedido.SOLICITADO
    assert pedido.parametros_extra["referencia_imagen"] == "org/app:v1.1"
    assert pedido.parametros_extra["instrucciones_uso"] == "Puerto web 3000."
    assert await db.scalar(select(func.count()).select_from(CompromisoCapacidad)) == 0

    # 4. Admin rechaza
    res_rechazar = await client.post(
        f"/pedidos/{pedido_id}/rechazar",
        json={"motivo": "No se cuenta con el soporte para esta tecnología en el cuatrimestre."},
        headers=auth_admin | {"Idempotency-Key": "aclaracion-rechazar"},
    )
    assert res_rechazar.status_code == 200
    await db.refresh(pedido)
    assert pedido.estado == EstadoPedido.RECHAZADO
    assert pedido.motivo_rechazo == "No se cuenta con el soporte para esta tecnología en el cuatrimestre."
    assert await db.scalar(select(func.count()).select_from(CompromisoCapacidad)) == 0
    assert len(proxmox.creados) == 0


@pytest.mark.parametrize("app_order", ["por_pedido"], indirect=True)
async def test_aprobacion_congela_revision_y_valores_sensibles_write_only(
    db, admin, app_order, proxmox
):
    app = app_order
    result, payload = await approve(db, admin, app, private={"APP_PASSWORD": "super-secret-pass"})
    saved = deepcopy(app.pedido.asignacion_snapshot)
    assert saved["configuracion_sha256"] == app.config.sha256
    assert saved["network_profile_id"] == "app-network"

    # Confirma que los valores privados no se guardan en claro en snapshots ni idempotencia
    decision = await db.scalar(select(DecisionIdempotente))
    secret = await db.scalar(select(SecretoDespliegue))
    assert "super-secret-pass" not in repr(app.pedido.asignacion_snapshot)
    assert "super-secret-pass" not in repr(app.pedido.decision_snapshot)
    assert "super-secret-pass" not in repr(decision.resultado_referencia)
    assert secret.valor_cifrado != "super-secret-pass"

    # Retirar la configuración de la oferta no altera la asignación ya aprobada
    app.config.estado = "retirada"
    app.config.retirada_at = clock.now()
    await db.commit()
    await db.refresh(app.pedido)
    assert app.pedido.asignacion_snapshot["configuracion_sha256"] == saved["configuracion_sha256"]
    assert app.pedido.configuracion_despliegue_id == app.config.id
