"""Pruebas para despacho de notificaciones por correo en el ciclo de vida de los pedidos."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pedido import Pedido, EstadoPedido
from app.models.catedra import Catedra
from app.models.usuario import Usuario
from tests import factories


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
):
    """Al crear o reenviar un pedido, los administradores reciben correo de alerta."""
    payload = {
        "catedra_id": catedra.id,
        "template_id": template.id,
        "modelo_servicio": "iaas",
        "vigencia_tipo": "anual",
        "descripcion_requerimientos": "Servidor para laboratorio",
    }

    mock_email.clear()
    res = await client.post("/pedidos/", json=payload, headers=auth_catedra)
    assert res.status_code == 201, res.text
    pedido_id = res.json()["id"]

    # Verificar que el admin recibió correo
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
        headers=auth_admin,
    )
    assert res_ajuste.status_code == 200, res_ajuste.text

    # Verificar que el docente recibió correo con las observaciones
    assert len(mock_email) >= 1
    mail_ajuste = mock_email[-1]
    assert usuario_catedra.email in mail_ajuste["destinatarios"]
    assert "Ajuste" in mail_ajuste["asunto"]
    assert "Reducir memoria RAM a 2GB" in mail_ajuste["texto_plano"]

    # Docente reenvía pedido
    mock_email.clear()
    res_reenviar = await client.post(
        f"/pedidos/{pedido_id}/reenviar",
        json={"descripcion_requerimientos": "Ajustado a 2GB de RAM"},
        headers=auth_catedra,
    )
    assert res_reenviar.status_code == 200, res_reenviar.text

    # Verificar que el admin vuelve a recibir correo informando el reenvío
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
):
    """Al rechazar un pedido, el docente solicitante recibe un correo con el motivo."""
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
        headers=auth_admin,
    )
    assert res.status_code == 200, res.text

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
):
    """Al completar exitosamente un despliegue, el solicitante recibe correo de servicio activo."""
    from app.services import orquestacion_service

    proxmox.nodos = [
        {
            "node": "pve1",
            "status": "online",
            "cpu": 0.1,
            "maxcpu": 8,
            "maxmem": 16 * 1024**3,
            "maxdisk": 100 * 1024**3,
        }
    ]

    pedido = await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario_catedra.id,
        template_id=template.id,
        estado=EstadoPedido.APROBADO,
    )
    pedido.reserva_vcpus = 1
    pedido.reserva_ram_mb = 512
    pedido.reserva_disk_gb = 4
    await db.commit()
    await db.refresh(pedido)

    mock_email.clear()
    servicio = await orquestacion_service.desplegar_pedido(
        db=db, pedido_id=pedido.id, admin=admin
    )
    assert servicio is not None

    # Verificar que el docente solicitante recibió la notificación de servicio activo
    assert len(mock_email) >= 1
    mail_activo = mock_email[-1]
    assert usuario_catedra.email in mail_activo["destinatarios"]
    assert "Activo" in mail_activo["asunto"]
    assert catedra.nombre in mail_activo["texto_plano"]


@pytest.mark.asyncio
async def test_despliegue_fallido_notifica_a_docente_y_administradores(
    db: AsyncSession,
    proxmox,
    usuario_catedra: Usuario,
    catedra: Catedra,
    template,
    admin: Usuario,
    mock_email: list[dict],
):
    """Si el aprovisionamiento en Proxmox falla, se notifica tanto al docente como a los administradores."""
    from fastapi import HTTPException
    from tests.fakes import ProxmoxFalla
    from app.services import orquestacion_service

    proxmox.nodos = [
        {
            "node": "pve1",
            "status": "online",
            "cpu": 0.1,
            "maxcpu": 8,
            "maxmem": 16 * 1024**3,
            "maxdisk": 100 * 1024**3,
        }
    ]
    proxmox.fallar_create = ProxmoxFalla("Almacenamiento no disponible en nodo pve1")

    pedido = await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario_catedra.id,
        template_id=template.id,
        estado=EstadoPedido.APROBADO,
    )
    pedido.reserva_vcpus = 1
    pedido.reserva_ram_mb = 512
    pedido.reserva_disk_gb = 4
    await db.commit()
    await db.refresh(pedido)

    mock_email.clear()
    with pytest.raises(HTTPException):
        await orquestacion_service.desplegar_pedido(
            db=db, pedido_id=pedido.id, admin=admin
        )

    # El docente y los administradores deben haber sido notificados del fallo
    assert len(mock_email) >= 1
    destinatarios_notificados = set()
    for mail in mock_email:
        destinatarios_notificados.update(mail["destinatarios"])
        if usuario_catedra.email in mail["destinatarios"]:
            assert "Error" in mail["asunto"] or "Fallo" in mail["asunto"]
            assert "Almacenamiento no disponible" in mail["texto_plano"]

    assert usuario_catedra.email in destinatarios_notificados
    assert admin.email in destinatarios_notificados

