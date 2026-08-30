"""Un fallo dentro de la tarea de Proxmox no puede pasar por éxito.

Las operaciones de Proxmox son asíncronas: `create_lxc` devuelve un
identificador de tarea y vuelve enseguida, mucho antes de que el contenedor
exista. El portal registraba el servicio como desplegado y en marcha en cuanto
recibía ese identificador, sin mirar nunca cómo terminó la tarea.

Encontrado el 2026-08-30 ejecutando la validación T041 de la feature 001 contra
el clúster real: se desplegó un pedido con una plantilla inexistente, Proxmox
respondió `unable to create CT 103 - volume ... does not exist`, y el portal
devolvió 200 con un servicio "running" cuyo contenedor nunca existió.

Rompe dos principios: queda un registro sin recurso real (III) y un estado que
no se corresponde con la realidad (II). Además consume capacidad reservada que
ningún contenedor usa.
"""

import pytest

from app.models.pedido import EstadoPedido
from app.services import orquestacion_service
from tests import factories

NODO = [
    {
        "node": "pve1",
        "status": "online",
        "cpu": 0.1,
        "maxcpu": 8,
        "maxmem": 16 * 1024**3,
        "maxdisk": 100 * 1024**3,
    }
]


@pytest.fixture(autouse=True)
def cluster(proxmox):
    proxmox.nodos = NODO
    return proxmox


async def _aprobado(db, catedra, usuario, template):
    pedido = await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario.id,
        template_id=template.id,
        estado=EstadoPedido.APROBADO,
    )
    pedido.reserva_vcpus = 1
    pedido.reserva_ram_mb = 256
    pedido.reserva_disk_gb = 4
    await db.commit()
    await db.refresh(pedido)
    return pedido


async def test_la_tarea_se_espera(db, catedra, usuario_catedra, template, admin, cluster):
    """El despliegue no puede darse por terminado antes que la tarea."""
    pedido = await _aprobado(db, catedra, usuario_catedra, template)

    await orquestacion_service.desplegar_pedido(db=db, pedido_id=pedido.id, admin=admin)

    assert cluster.tasks_esperadas, "se registró el servicio sin esperar a Proxmox"


async def test_si_la_tarea_falla_no_queda_un_servicio_fantasma(
    db, catedra, usuario_catedra, template, admin, cluster
):
    """El caso real: Proxmox acepta el pedido y después falla al ejecutarlo."""
    from app.models.servicio import Servicio
    from sqlalchemy import select

    pedido = await _aprobado(db, catedra, usuario_catedra, template)
    cluster.fallar_task = RuntimeError(
        "unable to create CT 103 - volume 'local:vztmpl/inexistente.tar.zst' does not exist"
    )

    with pytest.raises(Exception):
        await orquestacion_service.desplegar_pedido(
            db=db, pedido_id=pedido.id, admin=admin
        )

    servicios = (
        await db.execute(select(Servicio).where(Servicio.pedido_id == pedido.id))
    ).scalars().all()
    assert servicios == [], "quedó un registro de un contenedor que nunca existió"


async def test_el_pedido_queda_en_error_con_el_motivo(
    db, catedra, usuario_catedra, template, admin, cluster
):
    """Principio III: ante un fallo, estado explícito y motivo registrado."""
    pedido = await _aprobado(db, catedra, usuario_catedra, template)
    cluster.fallar_task = RuntimeError("volume does not exist")

    with pytest.raises(Exception):
        await orquestacion_service.desplegar_pedido(
            db=db, pedido_id=pedido.id, admin=admin
        )

    await db.refresh(pedido)
    assert pedido.estado == EstadoPedido.ERROR
    assert pedido.vmid_reservado is not None, "el VMID debe quedar para el reintento"


async def test_las_advertencias_no_son_un_fallo(
    db, catedra, usuario_catedra, template, admin, cluster
):
    """Proxmox devuelve "WARNINGS: n" en despliegues que sí funcionaron.

    Tratarlas como error dejaría en `error` contenedores perfectamente vivos —
    es lo que reporta el clúster real al arrancar un LXC sin algunas features
    del host.
    """
    pedido = await _aprobado(db, catedra, usuario_catedra, template)

    servicio = await orquestacion_service.desplegar_pedido(
        db=db, pedido_id=pedido.id, admin=admin
    )

    assert servicio is not None
