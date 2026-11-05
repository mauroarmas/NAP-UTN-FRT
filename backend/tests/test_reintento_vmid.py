"""US1 — resolución del VMID e identidad en despliegue y reintento."""

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.identidad_infraestructura import IdentidadInfraestructura
from app.models.pedido import EstadoPedido
from app.models.servicio import Servicio
from app.services import bootstrap_service
from app.worker import procesar_una
from tests import factories
from tests.capacity_helpers import aprobar_http, perfil_capacidad  # noqa: F401
from tests.fakes import ocupar
from tests.test_operaciones_recuperacion import prepared_guest  # noqa: F401


async def _aprobar_y_encolar(client, db, catedra, usuario_catedra, template, auth_admin):
    pedido = await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario_catedra.id,
        template_id=template.id,
        estado=EstadoPedido.SOLICITADO,
    )
    assert (await aprobar_http(client, pedido, template, auth_admin)).status_code == 200
    r = await client.post(
        f"/servicios/desplegar/{pedido.id}",
        headers=auth_admin | {"Idempotency-Key": f"dep-{uuid4()}"},
        json={},
    )
    assert r.status_code == 202, r.text
    return pedido


async def test_reserva_libre_se_reutiliza(
    client, engine, db, proxmox, catedra, usuario_catedra, template, auth_admin,
    perfil_capacidad, prepared_guest, monkeypatch
):
    """La identidad reclamada del despliegue fallido en bootstrap se reutiliza en el reintento."""
    proxmox.next_vmid = 150
    pedido = await _aprobar_y_encolar(
        client, db, catedra, usuario_catedra, template, auth_admin
    )

    async def _fallar(*args, **kwargs):
        return {"identity_verified": False, "local_health": False}

    monkeypatch.setattr(bootstrap_service, "preparar", _fallar)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await procesar_una(sessions, pve=proxmox)

    proxmox.next_vmid = 200  # si pidiera uno nuevo, sería 200
    llamadas_antes = proxmox.llamadas_next_vmid

    async def _ok(*args, **kwargs):
        return {
            "identity_verified": True,
            "local_health": True,
            "acceso_metadata": {"metodo": "consola", "validacion": "simulada"},
        }

    monkeypatch.setattr(bootstrap_service, "preparar", _ok)
    r = await client.post(
        f"/pedidos/{pedido.id}/reintentar",
        headers=auth_admin | {"Idempotency-Key": "reintento-reusa-150"},
        json={},
    )
    assert r.status_code == 202, r.text
    await procesar_una(sessions, pve=proxmox)

    servicio = await db.scalar(select(Servicio).where(Servicio.pedido_id == pedido.id))
    assert servicio.proxmox_vmid == "150"
    assert proxmox.llamadas_next_vmid == llamadas_antes
    assert len(proxmox.creados) == 1
    assert proxmox.creados[0]["vmid"] == 150


async def test_reserva_ocupada_por_tercero_pide_vmid_nuevo(
    client, engine, db, proxmox, catedra, usuario_catedra, template, auth_admin,
    perfil_capacidad, prepared_guest
):
    """Si el VMID devuelto por nextid ya está ocupado en el clúster, se salta al siguiente libre."""
    proxmox.next_vmid = 150
    pedido = await _aprobar_y_encolar(
        client, db, catedra, usuario_catedra, template, auth_admin
    )
    proxmox.recursos = [ocupar(150, "servidor-de-otra-catedra")]
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await procesar_una(sessions, pve=proxmox)

    servicio = await db.scalar(select(Servicio).where(Servicio.pedido_id == pedido.id))
    assert servicio is not None
    assert servicio.proxmox_vmid == "151"


async def test_huerfano_propio_se_adopta_sin_crear_otro(
    client, engine, db, proxmox, catedra, usuario_catedra, template, auth_admin,
    perfil_capacidad, prepared_guest, monkeypatch
):
    """research R2 — si el contenedor propio ya se creó, reparar no crea un segundo contenedor."""
    proxmox.next_vmid = 150
    pedido = await _aprobar_y_encolar(
        client, db, catedra, usuario_catedra, template, auth_admin
    )

    async def _fallar(*args, **kwargs):
        return {"identity_verified": False, "local_health": False}

    monkeypatch.setattr(bootstrap_service, "preparar", _fallar)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await procesar_una(sessions, pve=proxmox)
    assert len(proxmox.creados) == 1

    async def _ok(*args, **kwargs):
        return {
            "identity_verified": True,
            "local_health": True,
            "acceso_metadata": {"metodo": "consola", "validacion": "simulada"},
        }

    monkeypatch.setattr(bootstrap_service, "preparar", _ok)
    r = await client.post(
        f"/pedidos/{pedido.id}/reintentar",
        headers=auth_admin | {"Idempotency-Key": "reintento-huerfano-150"},
        json={},
    )
    assert r.status_code == 202, r.text
    await procesar_una(sessions, pve=proxmox)

    assert len(proxmox.creados) == 1
    servicios = (
        (await db.execute(select(Servicio).where(Servicio.pedido_id == pedido.id)))
        .scalars()
        .all()
    )
    assert len(servicios) == 1
    assert servicios[0].proxmox_vmid == "150"


async def test_sin_reserva_previa_pide_vmid_nuevo(
    client, engine, db, proxmox, catedra, usuario_catedra, template, auth_admin,
    perfil_capacidad, prepared_guest
):
    """Al desplegar sin identidad previa, reclama un VMID nuevo."""
    proxmox.next_vmid = 300
    pedido = await _aprobar_y_encolar(
        client, db, catedra, usuario_catedra, template, auth_admin
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await procesar_una(sessions, pve=proxmox)

    identidad = await db.scalar(
        select(IdentidadInfraestructura).where(
            IdentidadInfraestructura.pedido_alta_id == pedido.id
        )
    )
    assert identidad is not None
    assert identidad.vmid == 300
    assert proxmox.llamadas_next_vmid == 1
