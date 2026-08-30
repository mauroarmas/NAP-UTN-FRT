"""Un servicio con renovación pendiente no se apaga al vencer.

Si la cátedra pidió la renovación a tiempo y el administrador todavía no la
resolvió, apagar el servicio le cobra a la cátedra una demora que no es suya.
El sistema prefiere sostenerlo y señalarle al administrador que su demora está
afectando algo en uso.
"""

from datetime import datetime, timedelta

import pytest

from app.models.pedido import EstadoPedido
from app.models.servicio import EstadoServicio
from app.services import vencimiento_service
from tests import factories

NODO = [
    {
        "node": "pve1",
        "status": "online",
        "cpu": 0.1,
        "maxcpu": 16,
        "maxmem": 32 * 1024**3,
        "maxdisk": 200 * 1024**3,
    }
]


@pytest.fixture(autouse=True)
def cluster(proxmox):
    proxmox.nodos = NODO
    return proxmox


async def _vencido_con_renovacion(client, db, catedra, template, auth_catedra, vmid):
    servicio = await factories.crear_servicio(
        db, catedra_id=catedra.id, template_id=template.id, proxmox_vmid=vmid
    )
    # Se pide la renovación mientras el servicio todavía está vigente…
    servicio.vence_at = datetime.utcnow() + timedelta(days=2)
    await db.commit()
    r = await client.post(f"/servicios/{servicio.id}/renovar", headers=auth_catedra)
    assert r.status_code == 201, r.text

    # …y recién después llega la fecha de fin, sin que nadie la haya resuelto.
    servicio.vence_at = datetime.utcnow() - timedelta(hours=1)
    await db.commit()
    return servicio, r.json()["pedido_id"]


async def test_con_renovacion_pendiente_no_se_apaga(
    client, db, proxmox, catedra, template, auth_catedra
):
    servicio, _ = await _vencido_con_renovacion(
        client, db, catedra, template, auth_catedra, "700"
    )

    resultado = await vencimiento_service.aplicar_vencimientos(db)

    assert resultado["afectados"] == 0
    assert servicio.id in resultado["postergados_por_renovacion"]
    await db.refresh(servicio)
    assert servicio.estado == EstadoServicio.RUNNING
    assert proxmox.detenidos == []


async def test_la_demora_queda_visible_para_el_administrador(
    client, db, proxmox, catedra, template, auth_catedra
):
    """No alcanza con no apagarlo: hay que poder ver que algo está esperando."""
    servicio, _ = await _vencido_con_renovacion(
        client, db, catedra, template, auth_catedra, "701"
    )

    resultado = await vencimiento_service.aplicar_vencimientos(db)

    assert resultado["postergados_por_renovacion"] == [servicio.id]


async def test_resuelta_la_renovacion_el_servicio_sigue_vivo(
    client, db, proxmox, catedra, template, auth_catedra, auth_admin
):
    servicio, pedido_id = await _vencido_con_renovacion(
        client, db, catedra, template, auth_catedra, "702"
    )

    await client.post(f"/pedidos/{pedido_id}/aprobar", json={}, headers=auth_admin)
    await client.post(f"/servicios/desplegar/{pedido_id}", headers=auth_admin)

    resultado = await vencimiento_service.aplicar_vencimientos(db)

    assert resultado["afectados"] == 0
    await db.refresh(servicio)
    assert servicio.estado == EstadoServicio.RUNNING
    assert servicio.vence_at > datetime.utcnow()


async def test_rechazada_la_renovacion_el_servicio_si_vence(
    client, db, proxmox, catedra, template, auth_catedra, auth_admin
):
    """La protección es para la demora, no para la negativa.

    Si el administrador ya decidió que no, el vencimiento se aplica: sostenerlo
    indefinidamente convertiría un rechazo en una renovación silenciosa.
    """
    servicio, pedido_id = await _vencido_con_renovacion(
        client, db, catedra, template, auth_catedra, "703"
    )

    await client.post(
        f"/pedidos/{pedido_id}/rechazar",
        json={"motivo": "La materia terminó"},
        headers=auth_admin,
    )

    resultado = await vencimiento_service.aplicar_vencimientos(db)

    assert resultado["afectados"] == 1
    await db.refresh(servicio)
    assert servicio.estado == EstadoServicio.PAUSED
    assert servicio.deleted_at is None, "los datos siguen ahí"


async def test_sin_renovacion_pedida_el_servicio_vence(
    db, proxmox, catedra, template
):
    """Contraprueba: sin nada pendiente, la fecha se aplica normalmente."""
    servicio = await factories.crear_servicio(
        db, catedra_id=catedra.id, template_id=template.id, proxmox_vmid="704"
    )
    servicio.vence_at = datetime.utcnow() - timedelta(hours=1)
    await db.commit()

    resultado = await vencimiento_service.aplicar_vencimientos(db)

    assert resultado["afectados"] == 1
    assert resultado["postergados_por_renovacion"] == []
