"""Vencimiento de servicios y renovación por el mismo circuito de aprobación.

Es la vía **garantizada** de recuperación de capacidad: a diferencia del pausado
por inactividad, no depende de medir nada ni de que la recolección de métricas
esté sana. Una fecha de fin es determinista y predecible para la cátedra.

Lo que estas pruebas protegen: que renovar **no recree** el servicio, que no
reserve capacidad de más, y que un vencimiento no descuente dos veces lo que una
pausa ya liberó.
"""

from datetime import datetime, timedelta

import pytest

from app.models.pedido import EstadoPedido, TipoPedido, Pedido
from app.models.servicio import EstadoServicio
from app.models.servicio_historial import ServicioHistorial
from app.services import capacidad_service, vencimiento_service
from sqlalchemy import select
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


async def _servicio_con_vencimiento(db, catedra, template, vence_en_dias, vmid="600", **kw):
    servicio = await factories.crear_servicio(
        db, catedra_id=catedra.id, template_id=template.id, proxmox_vmid=vmid, **kw
    )
    servicio.vence_at = datetime.utcnow() + timedelta(days=vence_en_dias)
    await db.commit()
    return servicio


# --- El servicio nace con fecha conocida ---


async def test_el_servicio_desplegado_nace_con_fecha_de_vencimiento(
    client, db, catedra, usuario_catedra, template, auth_admin
):
    pedido = await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario_catedra.id,
        template_id=template.id,
        estado=EstadoPedido.SOLICITADO,
    )
    await client.post(f"/pedidos/{pedido.id}/aprobar", json={}, headers=auth_admin)

    r = await client.post(f"/servicios/desplegar/{pedido.id}", headers=auth_admin)

    assert r.status_code == 200, r.text
    assert r.json()["vence_at"] is not None, (
        "la cátedra tiene que saber desde el primer día hasta cuándo lo tiene"
    )


# --- Renovación ---


async def test_la_catedra_solicita_una_renovacion(
    client, db, catedra, template, auth_catedra
):
    servicio = await _servicio_con_vencimiento(db, catedra, template, 3)

    r = await client.post(f"/servicios/{servicio.id}/renovar", headers=auth_catedra)

    assert r.status_code == 201, r.text
    assert r.json()["servicio_id"] == servicio.id

    pedido = await db.get(Pedido, r.json()["pedido_id"])
    assert pedido.tipo == TipoPedido.RENOVACION
    assert pedido.estado == EstadoPedido.SOLICITADO


async def test_no_se_puede_pedir_dos_renovaciones_a_la_vez(
    client, db, catedra, template, auth_catedra
):
    servicio = await _servicio_con_vencimiento(db, catedra, template, 3, vmid="601")
    await client.post(f"/servicios/{servicio.id}/renovar", headers=auth_catedra)

    segunda = await client.post(
        f"/servicios/{servicio.id}/renovar", headers=auth_catedra
    )

    assert segunda.status_code == 409, segunda.text


async def test_la_renovacion_no_reserva_capacidad_nueva(
    client, db, catedra, template, auth_catedra, auth_admin
):
    """El servicio ya está desplegado y ya cuenta como consumo."""
    servicio = await _servicio_con_vencimiento(db, catedra, template, 3, vmid="602")
    r = await client.post(f"/servicios/{servicio.id}/renovar", headers=auth_catedra)
    pedido_id = r.json()["pedido_id"]

    antes = await capacidad_service.panorama(db)
    await client.post(f"/pedidos/{pedido_id}/aprobar", json={}, headers=auth_admin)
    despues = await capacidad_service.panorama(db)

    assert despues["reservado"] == antes["reservado"], (
        "contar la renovación como reserva sería contabilidad doble"
    )


async def test_la_renovacion_aprobada_conserva_el_servicio_y_corre_la_fecha(
    client, db, catedra, template, auth_catedra, auth_admin
):
    """Recrear el servicio le haría perder a la cátedra todo lo que tenía adentro."""
    servicio = await _servicio_con_vencimiento(db, catedra, template, 3, vmid="603")
    id_original = servicio.id
    vmid_original = servicio.proxmox_vmid
    vence_original = servicio.vence_at

    r = await client.post(f"/servicios/{servicio.id}/renovar", headers=auth_catedra)
    pedido_id = r.json()["pedido_id"]
    await client.post(f"/pedidos/{pedido_id}/aprobar", json={}, headers=auth_admin)

    desplegado = await client.post(
        f"/servicios/desplegar/{pedido_id}", headers=auth_admin
    )

    assert desplegado.status_code == 200, desplegado.text
    await db.refresh(servicio)
    assert servicio.id == id_original, "no se recrea el servicio"
    assert servicio.proxmox_vmid == vmid_original, "no se recrea el contenedor"
    assert servicio.vence_at > vence_original, "solo corre la fecha"


async def test_la_renovacion_queda_en_el_historial_del_servicio(
    client, db, catedra, template, auth_catedra, auth_admin
):
    servicio = await _servicio_con_vencimiento(db, catedra, template, 3, vmid="604")
    r = await client.post(f"/servicios/{servicio.id}/renovar", headers=auth_catedra)
    pedido_id = r.json()["pedido_id"]
    await client.post(f"/pedidos/{pedido_id}/aprobar", json={}, headers=auth_admin)
    await client.post(f"/servicios/desplegar/{pedido_id}", headers=auth_admin)

    entradas = (
        (
            await db.execute(
                select(ServicioHistorial).where(
                    ServicioHistorial.servicio_id == servicio.id
                )
            )
        )
        .scalars()
        .all()
    )
    assert any("Renovado" in (e.comentario or "") for e in entradas)


async def test_la_renovacion_rechazada_deja_ver_el_motivo(
    client, db, catedra, template, auth_catedra, auth_admin
):
    servicio = await _servicio_con_vencimiento(db, catedra, template, 3, vmid="605")
    r = await client.post(f"/servicios/{servicio.id}/renovar", headers=auth_catedra)
    pedido_id = r.json()["pedido_id"]

    await client.post(
        f"/pedidos/{pedido_id}/rechazar",
        json={"motivo": "La materia termina este cuatrimestre"},
        headers=auth_admin,
    )

    visto = await client.get(f"/pedidos/{pedido_id}", headers=auth_catedra)
    assert "cuatrimestre" in visto.json()["motivo_rechazo"]


async def test_no_se_renueva_un_servicio_ajeno(
    client, db, template, auth_catedra, usuario_multicatedra
):
    ajeno = await factories.crear_servicio(
        db,
        catedra_id=usuario_multicatedra.ajena.id,
        template_id=template.id,
        proxmox_vmid="606",
    )

    r = await client.post(f"/servicios/{ajeno.id}/renovar", headers=auth_catedra)

    assert r.status_code == 403, r.text


# --- Aplicación del vencimiento ---


async def test_avisa_antes_de_vencer(db, proxmox, catedra, template):
    servicio = await _servicio_con_vencimiento(db, catedra, template, 3, vmid="610")

    resultado = await vencimiento_service.aplicar_vencimientos(db)

    assert servicio.id in resultado["avisados"]
    assert resultado["afectados"] == 0
    await db.refresh(servicio)
    assert servicio.aviso_vencimiento_at is not None
    assert servicio.estado == EstadoServicio.RUNNING


async def test_el_servicio_vencido_libera_computo_sin_destruir_datos(
    db, proxmox, catedra, template
):
    servicio = await _servicio_con_vencimiento(db, catedra, template, -1, vmid="611")

    resultado = await vencimiento_service.aplicar_vencimientos(db)

    assert resultado["afectados"] == 1
    await db.refresh(servicio)
    assert servicio.estado == EstadoServicio.PAUSED
    assert servicio.deleted_at is None, "los datos no se destruyen automáticamente"
    assert ("pve1", 611) in proxmox.detenidos


async def test_el_vencimiento_queda_registrado_con_el_sistema_como_autor(
    db, proxmox, catedra, template
):
    servicio = await _servicio_con_vencimiento(db, catedra, template, -1, vmid="612")

    await vencimiento_service.aplicar_vencimientos(db)

    entradas = (
        (
            await db.execute(
                select(ServicioHistorial).where(
                    ServicioHistorial.servicio_id == servicio.id
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(entradas) == 1
    assert entradas[0].usuario_id is None
    assert "Vencido" in entradas[0].comentario


async def test_un_servicio_ya_pausado_no_descuenta_capacidad_dos_veces(
    db, proxmox, catedra, template
):
    """Vencimiento y pausado pueden alcanzar al mismo servicio.

    La pausa ya liberó su cómputo: el vencimiento solo tiene que dejar
    constancia, no volver a detener nada ni descontar de nuevo.
    """
    servicio = await _servicio_con_vencimiento(
        db, catedra, template, -1, vmid="613", estado=EstadoServicio.PAUSED
    )
    servicio.pausado_auto_at = datetime.utcnow()
    await db.commit()

    antes = await capacidad_service.panorama(db)
    resultado = await vencimiento_service.aplicar_vencimientos(db)
    despues = await capacidad_service.panorama(db)

    assert resultado["afectados"] == 1
    assert despues["desplegado"] == antes["desplegado"], (
        "la pausa ya había liberado el cómputo; no hay nada que descontar otra vez"
    )
    assert proxmox.detenidos == [], "no hay que volver a detener lo ya detenido"


async def test_sin_fecha_de_vencimiento_no_se_apaga_nada(
    db, proxmox, catedra, template
):
    """Los servicios anteriores a la feature no tienen fecha: no se los apaga.

    Apagar por vencimiento a un servicio que nunca supo que tenía fecha sería
    exactamente la sorpresa que el aviso previo existe para evitar.
    """
    await factories.crear_servicio(
        db, catedra_id=catedra.id, template_id=template.id, proxmox_vmid="614"
    )

    resultado = await vencimiento_service.aplicar_vencimientos(db)

    assert resultado["afectados"] == 0
    assert proxmox.detenidos == []


async def test_el_trabajo_es_ejecutable_a_mano(client, auth_admin):
    r = await client.post("/admin/jobs/aplicar_vencimientos", headers=auth_admin)

    assert r.status_code == 200, r.text
    assert r.json()["job"] == "aplicar_vencimientos"
