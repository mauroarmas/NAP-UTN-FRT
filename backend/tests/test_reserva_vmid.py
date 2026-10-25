"""US1 — persistencia de la identidad/VMID reclamada en infraestructura."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.identidad_infraestructura import IdentidadInfraestructura
from app.models.pedido import EstadoPedido
from app.models.servicio import Servicio
from app.services import bootstrap_service
from app.worker import procesar_una
from tests import factories
from tests.capacity_helpers import aprobar_http, perfil_capacidad  # noqa: F401
from tests.test_operaciones_recuperacion import prepared_guest  # noqa: F401


async def _encolar_despliegue(client, db, catedra, usuario_catedra, template, auth_admin, clave):
    pedido = await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario_catedra.id,
        template_id=template.id,
        estado=EstadoPedido.SOLICITADO,
    )
    r_ap = await aprobar_http(client, pedido, template, auth_admin)
    assert r_ap.status_code == 200, r_ap.text
    r_dep = await client.post(
        f"/servicios/desplegar/{pedido.id}",
        headers=auth_admin | {"Idempotency-Key": clave},
        json={},
    )
    assert r_dep.status_code == 202, r_dep.text
    return pedido


async def test_despliegue_fallido_conserva_el_vmid_reservado(
    client, engine, db, proxmox, catedra, usuario_catedra, template, auth_admin,
    perfil_capacidad, prepared_guest, monkeypatch
):
    """research R1 — la identidad reclamada sobrevive al fallo de preparación post-creación."""
    proxmox.next_vmid = 175
    pedido = await _encolar_despliegue(
        client, db, catedra, usuario_catedra, template, auth_admin, "vmid-fallo-1"
    )

    async def _fallar_bootstrap(*args, **kwargs):
        return {"identity_verified": False, "local_health": False}

    monkeypatch.setattr(bootstrap_service, "preparar", _fallar_bootstrap)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await procesar_una(sessions, pve=proxmox)

    await db.refresh(pedido)
    assert pedido.estado == EstadoPedido.ERROR
    identidad = await db.scalar(
        select(IdentidadInfraestructura).where(
            IdentidadInfraestructura.pedido_alta_id == pedido.id
        )
    )
    assert identidad is not None
    assert identidad.vmid == 175


async def test_despliegue_exitoso_tambien_registra_la_reserva(
    client, engine, db, proxmox, catedra, usuario_catedra, template, auth_admin,
    perfil_capacidad, prepared_guest
):
    proxmox.next_vmid = 180
    pedido = await _encolar_despliegue(
        client, db, catedra, usuario_catedra, template, auth_admin, "vmid-ok-1"
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await procesar_una(sessions, pve=proxmox)

    identidad = await db.scalar(
        select(IdentidadInfraestructura).where(
            IdentidadInfraestructura.pedido_alta_id == pedido.id
        )
    )
    servicio = await db.scalar(
        select(Servicio).where(Servicio.pedido_id == pedido.id)
    )
    assert identidad is not None and identidad.vmid == 180
    assert servicio is not None and servicio.proxmox_vmid == "180"
