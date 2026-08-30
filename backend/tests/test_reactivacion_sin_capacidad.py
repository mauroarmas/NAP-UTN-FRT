"""Reactivación de un servicio pausado por la propia cátedra.

Dos propiedades que sostienen el modelo:

- La cátedra reactiva **sola**. Si necesitara un pedido nuevo o la aprobación de
  un administrador, el pausado automático sería una denegación de servicio
  encubierta: el sistema apaga y después hay que pedir permiso para volver.
- Una reactivación que no puede completarse deja el servicio **pausado**, con el
  motivo explicado. Nunca en error ni en un estado ambiguo.
"""

from datetime import datetime

import pytest

from app.models.servicio import EstadoServicio
from app.models.servicio_historial import ServicioHistorial
from sqlalchemy import select
from tests import factories
from tests.fakes import ProxmoxFalla

CLUSTER_HOLGADO = [
    {
        "node": "pve1",
        "status": "online",
        "cpu": 0.1,
        "maxcpu": 16,
        "maxmem": 32 * 1024**3,
        "maxdisk": 200 * 1024**3,
    }
]

CLUSTER_SIN_LUGAR = [
    {
        "node": "pve1",
        "status": "online",
        "cpu": 0.9,
        "maxcpu": 1,
        "maxmem": 256 * 1024**2,
        "maxdisk": 200 * 1024**3,
    }
]


async def _pausado(db, catedra, template, vmid="500", **kwargs):
    servicio = await factories.crear_servicio(
        db,
        catedra_id=catedra.id,
        template_id=template.id,
        proxmox_vmid=vmid,
        estado=EstadoServicio.PAUSED,
        **kwargs,
    )
    servicio.pausado_auto_at = datetime.utcnow()
    await db.commit()
    return servicio


async def test_la_catedra_reactiva_su_servicio_sin_aprobacion(
    client, db, proxmox, catedra, template, auth_catedra
):
    proxmox.nodos = CLUSTER_HOLGADO
    servicio = await _pausado(db, catedra, template)

    r = await client.post(f"/servicios/{servicio.id}/reactivar", headers=auth_catedra)

    assert r.status_code == 200, r.text
    assert r.json()["estado"] == EstadoServicio.RUNNING.value
    await db.refresh(servicio)
    assert servicio.pausado_auto_at is None
    assert ("pve1", 500) in proxmox.iniciados


async def test_reactivar_limpia_la_pausa_programada(
    client, db, proxmox, catedra, template, auth_catedra
):
    proxmox.nodos = CLUSTER_HOLGADO
    servicio = await _pausado(db, catedra, template, vmid="501")
    servicio.pausa_programada_at = datetime.utcnow()
    servicio.aviso_pausa_at = datetime.utcnow()
    await db.commit()

    await client.post(f"/servicios/{servicio.id}/reactivar", headers=auth_catedra)

    await db.refresh(servicio)
    assert servicio.pausa_programada_at is None
    assert servicio.aviso_pausa_at is None


async def test_la_reactivacion_queda_en_el_historial_con_su_autor(
    client, db, proxmox, catedra, template, auth_catedra, usuario_catedra
):
    proxmox.nodos = CLUSTER_HOLGADO
    servicio = await _pausado(db, catedra, template, vmid="502")

    await client.post(f"/servicios/{servicio.id}/reactivar", headers=auth_catedra)

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
    # A diferencia de la pausa, esto sí lo decidió una persona.
    assert entradas[0].usuario_id == usuario_catedra.id
    assert entradas[0].estado_nuevo == EstadoServicio.RUNNING.value


async def test_sin_capacidad_queda_pausado_y_no_en_error(
    client, db, proxmox, catedra, template, auth_catedra
):
    """El escenario que la spec exige que no deje el servicio en estado ambiguo."""
    proxmox.nodos = CLUSTER_SIN_LUGAR
    servicio = await _pausado(
        db, catedra, template, vmid="503", vcpus=8, ram_mb=16384
    )

    r = await client.post(f"/servicios/{servicio.id}/reactivar", headers=auth_catedra)

    assert r.status_code == 409, r.text
    assert r.json()["detail"]["codigo"] == "sin_capacidad"
    # El mensaje tiene que decirle qué hacer, no solo que falló.
    assert "administrador" in r.json()["detail"]["mensaje"]

    await db.refresh(servicio)
    assert servicio.estado == EstadoServicio.PAUSED, "nunca en error"
    assert servicio.pausado_auto_at is not None
    assert proxmox.iniciados == [], "no debe tocarse la infraestructura si no hay lugar"


async def test_un_fallo_de_infraestructura_da_502(
    client, db, proxmox, catedra, template, auth_catedra
):
    proxmox.nodos = CLUSTER_HOLGADO
    proxmox.fallar_start = ProxmoxFalla("nodo caído")
    servicio = await _pausado(db, catedra, template, vmid="504")

    r = await client.post(f"/servicios/{servicio.id}/reactivar", headers=auth_catedra)

    assert r.status_code == 502, r.text
    await db.refresh(servicio)
    assert servicio.estado == EstadoServicio.PAUSED


async def test_no_se_reactiva_lo_que_no_esta_pausado(
    client, db, proxmox, catedra, template, auth_catedra
):
    proxmox.nodos = CLUSTER_HOLGADO
    servicio = await factories.crear_servicio(
        db,
        catedra_id=catedra.id,
        template_id=template.id,
        proxmox_vmid="505",
        estado=EstadoServicio.RUNNING,
    )

    r = await client.post(f"/servicios/{servicio.id}/reactivar", headers=auth_catedra)

    assert r.status_code == 409, r.text


async def test_no_se_reactiva_un_servicio_ajeno(
    client, db, proxmox, template, auth_catedra, usuario_multicatedra
):
    proxmox.nodos = CLUSTER_HOLGADO
    ajeno = await _pausado(
        db, usuario_multicatedra.ajena, template, vmid="506"
    )

    r = await client.post(f"/servicios/{ajeno.id}/reactivar", headers=auth_catedra)

    assert r.status_code == 403, r.text


# --- Marca "siempre encendido" y listados del administrador ---


async def test_la_catedra_marca_su_servicio_como_siempre_encendido(
    client, db, proxmox, catedra, template, auth_catedra
):
    servicio = await factories.crear_servicio(
        db, catedra_id=catedra.id, template_id=template.id, proxmox_vmid="510"
    )

    r = await client.patch(
        f"/servicios/{servicio.id}",
        json={"exento_pausado": True},
        headers=auth_catedra,
    )

    assert r.status_code == 200, r.text
    assert r.json()["exento_pausado"] is True


async def test_marcar_exento_cancela_la_pausa_anunciada(
    client, db, proxmox, catedra, template, auth_catedra
):
    """Avisar de una pausa que ya no va a ocurrir sería incoherente."""
    servicio = await factories.crear_servicio(
        db, catedra_id=catedra.id, template_id=template.id, proxmox_vmid="511"
    )
    servicio.pausa_programada_at = datetime.utcnow()
    servicio.aviso_pausa_at = datetime.utcnow()
    await db.commit()

    await client.patch(
        f"/servicios/{servicio.id}",
        json={"exento_pausado": True},
        headers=auth_catedra,
    )

    await db.refresh(servicio)
    assert servicio.pausa_programada_at is None


async def test_la_catedra_no_puede_cambiar_el_vencimiento(
    client, db, proxmox, catedra, template, auth_catedra
):
    """Correr una fecha de fin es una decisión sobre capacidad."""
    servicio = await factories.crear_servicio(
        db, catedra_id=catedra.id, template_id=template.id, proxmox_vmid="512"
    )

    r = await client.patch(
        f"/servicios/{servicio.id}",
        json={"vence_at": "2030-01-01T00:00:00"},
        headers=auth_catedra,
    )

    assert r.status_code == 403, r.text


async def test_el_admin_ve_los_pausados_con_su_antiguedad(
    client, db, proxmox, catedra, template, auth_admin
):
    await _pausado(db, catedra, template, vmid="520", disk_gb=8)

    r = await client.get("/servicios/pausados", headers=auth_admin)

    assert r.status_code == 200, r.text
    fila = r.json()[0]
    assert fila["dias_pausado"] == 0
    # El disco sigue ocupado aunque el cómputo se haya liberado.
    assert fila["disk_asignado_gb"] == 8


async def test_los_pausados_son_solo_para_el_admin(client, auth_catedra):
    r = await client.get("/servicios/pausados", headers=auth_catedra)

    assert r.status_code == 403, r.text


async def test_el_admin_ve_los_exentos_que_igual_estan_inactivos(
    client, db, proxmox, catedra, template, auth_admin
):
    """Contrapeso a que la exención se use de más."""
    from tests.test_inactividad_pausado import _sembrar

    servicio = await factories.crear_servicio(
        db,
        catedra_id=catedra.id,
        template_id=template.id,
        proxmox_vmid="530",
        estado=EstadoServicio.RUNNING,
    )
    servicio.exento_pausado = True
    await db.commit()
    await _sembrar(db, servicio.id)

    r = await client.get("/servicios/exentos-inactivos", headers=auth_admin)

    assert r.status_code == 200, r.text
    assert [s["id"] for s in r.json()] == [servicio.id]
