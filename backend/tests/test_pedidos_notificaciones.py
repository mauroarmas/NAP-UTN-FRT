"""Pruebas para despacho de notificaciones por outbox en el ciclo de vida de los pedidos."""

from datetime import timedelta
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.pedido import EstadoPedido
from app.models.catedra import Catedra
from app.models.usuario import Usuario
from app.services import notificacion_service, orquestacion_service
from app.utils.clock import clock
from app.worker import procesar_una
from tests import factories
from tests.capacity_helpers import aprobar_http, materializado, perfil_capacidad  # noqa: F401
from tests.test_operaciones_recuperacion import prepared_guest  # noqa: F401


def _vigencia():
    hoy = clock.now().astimezone(ZoneInfo("America/Argentina/Tucuman")).date()
    return {
        "tipo": "personalizado",
        "desde": hoy.isoformat(),
        "hasta": (hoy + timedelta(days=30)).isoformat(),
    }


async def _despachar_outbox(db: AsyncSession):
    while await notificacion_service.procesar_uno(db):
        pass


@pytest.mark.asyncio
async def test_crear_y_reenviar_pedido_notifica_a_administradores(
    client: AsyncClient,
    db: AsyncSession,
    auth_catedra: dict,
    auth_admin: dict,
    usuario_catedra: Usuario,
    catedra: Catedra,
    admin: Usuario,
    template,
    mock_email: list[dict],
    perfil_capacidad,
):
    """Al crear o reenviar un pedido, se encola y despacha correo de alerta a administradores."""
    payload = {
        "catedra_id": catedra.id,
        "template_id": template.id,
        "modelo_servicio": "iaas",
        "vigencia": _vigencia(),
        "descripcion_requerimientos": "Servidor para laboratorio",
    }

    mock_email.clear()
    res = await client.post(
        "/pedidos/",
        json=payload,
        headers=auth_catedra | {"Idempotency-Key": "notif-crear-1"},
    )
    assert res.status_code == 201, res.text
    pedido_id = res.json()["id"]

    await _despachar_outbox(db)
    assert len(mock_email) >= 1
    mail_creacion = mock_email[-1]
    assert admin.email in mail_creacion["destinatarios"]
    assert "Nuevo Pedido" in mail_creacion["asunto"]
    assert catedra.nombre in mail_creacion["texto_plano"]

    # Admin solicita ajuste
    mock_email.clear()
    res_ajuste = await client.post(
        f"/pedidos/{pedido_id}/solicitar-ajuste",
        json={"observaciones": "Reducir memoria RAM a 2GB"},
        headers=auth_admin | {"Idempotency-Key": "notif-ajuste-1"},
    )
    assert res_ajuste.status_code == 200, res_ajuste.text

    await _despachar_outbox(db)
    assert len(mock_email) >= 1
    mail_ajuste = mock_email[-1]
    assert usuario_catedra.email in mail_ajuste["destinatarios"]
    assert "Aclaración" in mail_ajuste["asunto"]
    assert "Reducir memoria RAM a 2GB" in mail_ajuste["texto_plano"]

    # Administración incorpora las correcciones y reenvía
    mock_email.clear()
    res_reenviar = await client.post(
        f"/pedidos/{pedido_id}/reenviar",
        json={
            "descripcion_requerimientos": "Ajustado a 2GB de RAM",
            "vigencia": _vigencia(),
        },
        headers=auth_catedra | {"Idempotency-Key": "notif-reenviar-1"},
    )
    assert res_reenviar.status_code == 200, res_reenviar.text

    await _despachar_outbox(db)
    assert len(mock_email) >= 1
    mail_reenvio = mock_email[-1]
    assert admin.email in mail_reenvio["destinatarios"]
    assert "Reenviado" in mail_reenvio["asunto"]


@pytest.mark.asyncio
async def test_rechazar_pedido_notifica_al_docente(
    client: AsyncClient,
    db: AsyncSession,
    auth_admin: dict,
    usuario_catedra: Usuario,
    catedra: Catedra,
    template,
    mock_email: list[dict],
    perfil_capacidad,
):
    """Al rechazar un pedido, el docente titular recibe un correo con el motivo vía outbox."""
    pedido = await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario_catedra.id,
        template_id=template.id,
        estado=EstadoPedido.SOLICITADO,
    )

    mock_email.clear()
    res = await client.post(
        f"/pedidos/{pedido.id}/rechazar",
        json={"motivo": "Sin capacidad disponible en clúster"},
        headers=auth_admin | {"Idempotency-Key": "notif-rechazar-1"},
    )
    assert res.status_code == 200, res.text

    await _despachar_outbox(db)
    assert len(mock_email) >= 1
    mail_rechazo = mock_email[-1]
    assert usuario_catedra.email in mail_rechazo["destinatarios"]
    assert "Rechazado" in mail_rechazo["asunto"]
    assert "Sin capacidad disponible en clúster" in mail_rechazo["texto_plano"]


@pytest.mark.asyncio
async def test_despliegue_exitoso_notifica_servicio_activo(
    db: AsyncSession,
    proxmox,
    usuario_catedra: Usuario,
    catedra: Catedra,
    template,
    admin: Usuario,
    mock_email: list[dict],
    perfil_capacidad,
):
    """Cuando el acceso del servicio desplegado se verifica, el titular recibe correo de servicio activo."""
    servicio, _ = await materializado(
        db, proxmox, catedra, usuario_catedra, template
    )

    mock_email.clear()
    await notificacion_service.encolar_acceso_verificado(
        db, servicio, preparation_id="prep-test-009"
    )
    await db.commit()
    await _despachar_outbox(db)

    assert len(mock_email) >= 1
    mail_activo = mock_email[-1]
    assert usuario_catedra.email in mail_activo["destinatarios"]
    assert "Activo" in mail_activo["asunto"]
    assert catedra.nombre in mail_activo["texto_plano"]


@pytest.mark.asyncio
async def test_despliegue_fallido_notifica_a_docente_y_administradores(
    client: AsyncClient,
    engine,
    db: AsyncSession,
    proxmox,
    usuario_catedra: Usuario,
    catedra: Catedra,
    template,
    admin: Usuario,
    auth_admin: dict,
    mock_email: list[dict],
    perfil_capacidad,
    prepared_guest,
):
    """Si la tarea de despliegue en Proxmox falla, se encola alerta tanto al docente como a los administradores."""
    pedido = await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario_catedra.id,
        template_id=template.id,
        estado=EstadoPedido.SOLICITADO,
    )
    resp_aprobar = await aprobar_http(client, pedido, template, auth_admin)
    assert resp_aprobar.status_code == 200, resp_aprobar.text

    resp_deploy = await client.post(
        f"/servicios/desplegar/{pedido.id}",
        headers=auth_admin | {"Idempotency-Key": "deploy-fallido-notif"},
        json={},
    )
    assert resp_deploy.status_code == 202, resp_deploy.text
    proxmox.configure_task(
        "pve1",
        "UPID:pve1:task:create",
        [{"status": "stopped", "exitstatus": "ERROR: Almacenamiento no disponible"}],
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await procesar_una(sessions, pve=proxmox)

    mock_email.clear()
    await _despachar_outbox(db)

    assert len(mock_email) >= 1
    destinatarios_notificados = set()
    for mail in mock_email:
        destinatarios_notificados.update(mail["destinatarios"])
        if usuario_catedra.email in mail["destinatarios"]:
            assert "Error" in mail["asunto"] or "Fallo" in mail["asunto"]
            assert "tarea_fallida" in mail["texto_plano"]

    assert usuario_catedra.email in destinatarios_notificados
    assert admin.email in destinatarios_notificados

