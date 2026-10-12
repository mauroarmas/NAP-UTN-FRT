import pytest
from app.models.pedido import EstadoPedido, ModeloServicio, VigenciaTipo
from tests import factories


async def test_admin_solicitar_ajuste_exitoso(
    client, db, catedra, usuario_catedra, template, auth_admin
):
    """El administrador devuelve un pedido a la cátedra con observaciones obligatorias."""
    pedido = await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario_catedra.id,
        template_id=template.id,
        estado=EstadoPedido.SOLICITADO,
        descripcion_requerimientos="Servicio inicial",
    )

    r = await client.post(
        f"/pedidos/{pedido.id}/solicitar-ajuste",
        json={"observaciones": "Por favor reducir la memoria solicitada o justificar el uso."},
        headers=auth_admin,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["estado"] == "requiere_ajuste"
    assert data["observaciones_ajuste"] == "Por favor reducir la memoria solicitada o justificar el uso."


async def test_admin_solicitar_ajuste_sin_observaciones_falla(
    client, db, catedra, usuario_catedra, template, auth_admin
):
    """Solicitar un ajuste sin observaciones es rechazado con 400."""
    pedido = await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario_catedra.id,
        template_id=template.id,
        estado=EstadoPedido.SOLICITADO,
    )

    r = await client.post(
        f"/pedidos/{pedido.id}/solicitar-ajuste",
        json={"observaciones": "   "},
        headers=auth_admin,
    )
    assert r.status_code == 400


async def test_catedra_reenviar_pedido_tras_ajustes(
    client, db, catedra, usuario_catedra, template, auth_catedra
):
    """La cátedra actualiza y reenvía un pedido en REQUIERE_AJUSTE volviendo a SOLICITADO."""
    pedido = await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario_catedra.id,
        template_id=template.id,
        estado=EstadoPedido.REQUIERE_AJUSTE,
        descripcion_requerimientos="Versión previa",
    )

    r = await client.post(
        f"/pedidos/{pedido.id}/reenviar",
        json={
            "descripcion_requerimientos": "Versión corregida con memoria reducida",
            "vigencia_tipo": "segundo_cuatrimestre",
        },
        headers=auth_catedra,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["estado"] == "solicitado"
    assert data["descripcion_requerimientos"] == "Versión corregida con memoria reducida"
    assert data["vigencia_tipo"] == "segundo_cuatrimestre"


async def test_catedra_cancelar_pedido_en_ajuste(
    client, db, catedra, usuario_catedra, template, auth_catedra
):
    """La cátedra puede cancelar voluntariamente un pedido que requiere ajuste."""
    pedido = await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario_catedra.id,
        template_id=template.id,
        estado=EstadoPedido.REQUIERE_AJUSTE,
    )

    r = await client.post(
        f"/pedidos/{pedido.id}/cancelar",
        json={"motivo": "Ya no requerimos este entorno para este ciclo."},
        headers=auth_catedra,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["estado"] == "cancelado"


async def test_rechazo_con_motivo_vacio_falla(
    client, db, catedra, usuario_catedra, template, auth_admin
):
    """El motivo de rechazo es obligatorio tanto a nivel Pydantic como de servicio."""
    pedido = await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario_catedra.id,
        template_id=template.id,
        estado=EstadoPedido.SOLICITADO,
    )

    r = await client.post(
        f"/pedidos/{pedido.id}/rechazar",
        json={"motivo": "   "},
        headers=auth_admin,
    )
    assert r.status_code == 400

