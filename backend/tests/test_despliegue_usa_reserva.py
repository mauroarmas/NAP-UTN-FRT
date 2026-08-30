"""El despliegue usa lo que el pedido reservó, no lo que la plantilla dice hoy.

Aprobar un pedido **compromete** capacidad: el sistema guarda en el propio pedido
los tres números que reservó. Si el despliegue leyera la plantilla en vez de esa
reserva, editar la plantilla entre la aprobación y el despliegue haría que el
contenedor se creara con valores que nadie aprobó, sobrecomprometiendo el clúster
sin dejar rastro en ningún historial.

Hasta la feature 006 ese escenario era inalcanzable porque las plantillas no se
podían editar. Habilitar la edición lo vuelve posible, así que estas pruebas son
la compuerta que impide que la corrección de plantillas introduzca una fuga de
capacidad (FR-018, R2).
"""

import pytest

from app.models.pedido import EstadoPedido
from app.models.servicio import EstadoServicio
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


async def _aprobado_con_reserva(db, catedra, usuario, template, vcpus, ram_mb, disk_gb):
    """Un pedido aprobado cuya reserva quedó fijada en el momento de aprobar."""
    pedido = await factories.crear_pedido(
        db,
        catedra_id=catedra.id,
        solicitante_id=usuario.id,
        template_id=template.id,
        estado=EstadoPedido.APROBADO,
    )
    pedido.reserva_vcpus = vcpus
    pedido.reserva_ram_mb = ram_mb
    pedido.reserva_disk_gb = disk_gb
    await db.commit()
    await db.refresh(pedido)
    return pedido


async def test_la_plantilla_cambia_entre_aprobar_y_desplegar(
    db, catedra, usuario_catedra, template, admin, cluster
):
    """El escenario que esta feature vuelve alcanzable.

    Se aprueba por 1 vCPU, se agranda la plantilla, se despliega: el contenedor
    tiene que salir con 1, no con lo que la plantilla dice ahora.
    """
    pedido = await _aprobado_con_reserva(
        db, catedra, usuario_catedra, template, vcpus=1, ram_mb=256, disk_gb=4
    )

    # El administrador corrige la plantilla y la deja mucho más grande.
    template.default_vcpus = 4
    template.default_ram_mb = 4096
    template.default_disk_gb = 16
    await db.commit()

    await orquestacion_service.desplegar_pedido(db=db, pedido_id=pedido.id, admin=admin)

    creado = cluster.creados[-1]
    assert creado["cores"] == 1, "el contenedor tomó los vCPU de la plantilla editada"
    assert creado["memory"] == 256
    assert creado["rootfs"].endswith(":4")


async def test_el_servicio_se_registra_con_lo_reservado(
    db, catedra, usuario_catedra, template, admin, cluster
):
    """Lo reservado, lo desplegado y lo registrado tienen que coincidir (P2)."""
    pedido = await _aprobado_con_reserva(
        db, catedra, usuario_catedra, template, vcpus=2, ram_mb=512, disk_gb=8
    )

    template.default_vcpus = 8
    template.default_ram_mb = 8192
    template.default_disk_gb = 32
    await db.commit()

    servicio = await orquestacion_service.desplegar_pedido(
        db=db, pedido_id=pedido.id, admin=admin
    )

    assert servicio.vcpus_asignados == 2
    assert servicio.ram_asignada_mb == 512
    assert servicio.disk_asignado_gb == 8


async def test_sin_editar_la_plantilla_el_resultado_no_cambia(
    db, catedra, usuario_catedra, template, admin, cluster
):
    """Regresión: para todo pedido cuya plantilla no cambió, nada se altera.

    Es lo que garantiza que la corrección no tenga efectos sobre los pedidos ya
    aprobados antes de esta feature, cuya reserva coincide con la plantilla.
    """
    pedido = await _aprobado_con_reserva(
        db,
        catedra,
        usuario_catedra,
        template,
        vcpus=template.default_vcpus,
        ram_mb=template.default_ram_mb,
        disk_gb=template.default_disk_gb,
    )

    servicio = await orquestacion_service.desplegar_pedido(
        db=db, pedido_id=pedido.id, admin=admin
    )

    creado = cluster.creados[-1]
    assert creado["cores"] == template.default_vcpus
    assert servicio.ram_asignada_mb == template.default_ram_mb


async def test_la_plantilla_encogida_tampoco_manda(
    db, catedra, usuario_catedra, template, admin, cluster
):
    """El desacople es simétrico: achicar la plantilla tampoco cambia lo aprobado.

    Entregar menos de lo aprobado es menos peligroso para el clúster, pero igual
    de incorrecto: la cátedra recibiría un servicio distinto del que se le aprobó.
    """
    pedido = await _aprobado_con_reserva(
        db, catedra, usuario_catedra, template, vcpus=4, ram_mb=2048, disk_gb=8
    )

    template.default_vcpus = 1
    template.default_ram_mb = 256
    template.default_disk_gb = 2
    await db.commit()

    servicio = await orquestacion_service.desplegar_pedido(
        db=db, pedido_id=pedido.id, admin=admin
    )

    assert servicio.vcpus_asignados == 4
    assert servicio.ram_asignada_mb == 2048


async def test_si_la_infraestructura_falla_no_queda_servicio_a_medias(
    db, catedra, usuario_catedra, template, admin, cluster
):
    """Camino de fallo exigido por la compuerta constitucional.

    Que el despliegue lea la reserva no debe alterar el manejo de errores: ante
    un fallo de Proxmox el pedido queda en un estado explícito y sin servicio
    huérfano.
    """
    pedido = await _aprobado_con_reserva(
        db, catedra, usuario_catedra, template, vcpus=1, ram_mb=256, disk_gb=4
    )
    cluster.fallar_create = RuntimeError("Proxmox no responde")

    with pytest.raises(Exception):
        await orquestacion_service.desplegar_pedido(
            db=db, pedido_id=pedido.id, admin=admin
        )

    await db.refresh(pedido)
    assert pedido.estado == EstadoPedido.ERROR
    assert pedido.reserva_vcpus == 1, "la reserva no debe perderse ante un fallo"
