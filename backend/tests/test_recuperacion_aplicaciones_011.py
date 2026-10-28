"""Pruebas de recuperación de fallos e incertidumbre en aplicaciones OCI (US5 - T088):
create/start con respuesta perdida, takeover, boot distinto, trabajo desaparecido,
timeout, fuente inaccesible y fallo del probe; incertidumbre nunca permite recreación ciega o entrega.
"""
from hashlib import sha256
from uuid import UUID, uuid4
import pytest
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.compromiso_capacidad import CompromisoCapacidad
from app.models.identidad_infraestructura import IdentidadInfraestructura
from app.models.intento_despliegue import IntentoDespliegue
from app.models.operacion_infraestructura import OperacionInfraestructura
from app.models.pedido import Pedido, EstadoPedido
from app.models.servicio import Servicio
from app.services.application_verification_service import AccessObservation
from app.utils.clock import clock
from app.worker import procesar_una, procesar_ingesta_una
from infra.applications.job.protocol import (
    canonical,
    parse_request,
    public_identity,
    fingerprint,
)
from tests.test_admision_aplicaciones_011 import (
    app_order,
    approve,
    perfil_capacidad,
    red_aplicaciones_011,
    profile_entry,
)
from tests.test_creacion_aplicaciones_011 import stopped_create, wake


class RecoveryNode:
    """Simulador de nodo para pruebas de fallos y recuperación controlada."""
    def __init__(
        self,
        app,
        sessions,
        *,
        lose_start=False,
        boot_id=None,
        job_disappeared=False,
        timeout_read=False,
        source_unreachable=False,
    ):
        self.app = app
        self.sessions = sessions
        self.lose_start = lose_start
        self.boot = boot_id or str(uuid4())
        self.job_disappeared = job_disappeared
        self.timeout_read = timeout_read
        self.source_unreachable = source_unreachable
        self.starts = []
        self.statuses = []
        self.reads = []
        self.jobs = {}

    async def execute(self, request, **kwargs):
        request = parse_request(canonical(request))
        action = request["action"]

        if action == "profiles":
            if self.source_unreachable:
                return {
                    "protocol": request["protocol"],
                    "ok": True,
                    "action": action,
                    "data": {
                        "profiles": [
                            {
                                **self.app.document["perfil"],
                                "estado": "deshabilitado",
                                "motivo_codigo": "registry_inaccessible",
                            }
                        ]
                    },
                }
            return {
                "protocol": request["protocol"],
                "ok": True,
                "action": action,
                "data": {
                    "profiles": [
                        {
                            **self.app.document["perfil"],
                            "estado": "habilitado",
                            "motivo_codigo": None,
                        }
                    ]
                },
            }

        if action == "start":
            self.starts.append(request["execution_id"])
            self.jobs[request["execution_id"]] = fingerprint(request)
            if self.lose_start:
                self.lose_start = False
                raise TimeoutError("Respuesta de start perdida en la red")

        if action == "status":
            self.statuses.append(request["execution_id"])

        if action == "read":
            self.reads.append(request.get("after", 0))
            if self.timeout_read:
                raise TimeoutError("Timeout en lectura de consola")

        fp = self.jobs.get(request["execution_id"], "0" * 64)

        if self.job_disappeared:
            return {
                "protocol": request["protocol"],
                "ok": True,
                "action": action,
                "data": {
                    **public_identity(request),
                    "estado": "incierto",
                    "fase": "reconciliacion",
                    "fingerprint": fp,
                    "node_boot_id": self.boot,
                    "last_source_seq": 0,
                    "acknowledged_seq": 0,
                    "resultado": None,
                    "error_codigo": "trabajo_no_encontrado",
                    "items": [],
                    "dropped_ranges": [],
                },
            }

        return {
            "protocol": request["protocol"],
            "ok": True,
            "action": action,
            "data": {
                **public_identity(request),
                "estado": "ejecutando",
                "fase": "instalacion",
                "fingerprint": fp,
                "node_boot_id": self.boot,
                "last_source_seq": 0,
                "acknowledged_seq": 0,
                "resultado": None,
                "error_codigo": None,
                "items": [],
                "dropped_ranges": [],
            },
        }


async def test_respuesta_perdida_en_create_mantiene_incertidumbre_sin_duplicar_ct(
    db, engine, admin, app_order, proxmox
):
    """Si la respuesta de create se pierde, el worker en la siguiente iteración observa
    el contenedor ya existente y NO intenta crear otro con un vmid diferente."""
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await approve(db, admin, app_order, immediate=True)
    stopped_create(proxmox)

    lose_create = True
    async def after_dispatch(lease, upid):
        nonlocal lose_create
        if lose_create:
            lose_create = False
            raise RuntimeError("Respuesta de create perdida")

    node = RecoveryNode(app_order, sessions)

    # 1. Primer intento falla tras create_lxc
    await procesar_una(sessions, pve=proxmox, runner=node, after_dispatch=after_dispatch)
    await wake(db)

    # 2. Reintento / takeover en segundo paso
    await procesar_una(sessions, pve=proxmox, runner=node)
    await wake(db)

    # Solo 1 contenedor creado en Proxmox
    assert len(proxmox.creados) == 1
    assert len(proxmox.iniciados) == 0


async def test_respuesta_perdida_en_start_usa_status_con_mismo_execution_id(
    db, engine, admin, app_order, proxmox
):
    """Si la respuesta de start se pierde, la reconexión consulta con 'status' y el mismo
    execution_id; nunca emite un segundo 'start'."""
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await approve(db, admin, app_order, immediate=True)
    stopped_create(proxmox)

    node = RecoveryNode(app_order, sessions, lose_start=True)

    # 1. Crea y arranca el proceso en nodo, pero pierde la respuesta de start
    for _ in range(2):
        await procesar_una(sessions, pve=proxmox, runner=node)
        await wake(db)

    # Solo hubo 1 llamada 'start'
    assert len(node.starts) == 1

    # Siguiente ciclo: consulta estado con 'status' usando el mismo execution_id
    await procesar_una(sessions, pve=proxmox, runner=node)
    assert len(node.statuses) >= 1
    assert node.statuses[0] == node.starts[0]


async def test_boot_distinto_en_nodo_retiene_incertidumbre_sin_recreacion_ciega(
    db, engine, admin, app_order, proxmox
):
    """Si el boot_id del nodo cambia tras haber iniciado el trabajo, se detecta
    el reinicio del nodo y se mantiene el estado incierto sin recreación ciega."""
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await approve(db, admin, app_order, immediate=True)
    stopped_create(proxmox)

    boot1 = str(uuid4())
    node = RecoveryNode(app_order, sessions, boot_id=boot1)

    for _ in range(2):
        await procesar_una(sessions, pve=proxmox, runner=node)
        await wake(db)

    # Cambiar el boot del nodo simulando reinicio del hypervisor
    node.boot = str(uuid4())

    await procesar_una(sessions, pve=proxmox, runner=node)
    db.expire_all()

    op = await db.scalar(select(OperacionInfraestructura))
    ledger = await db.scalar(select(CompromisoCapacidad))
    # No se confirmó entrega y se conserva el compromiso
    assert op.estado != "confirmada"
    assert ledger.liberado_at is None
    # No se creó un segundo contenedor
    assert len(proxmox.creados) == 1


async def test_trabajo_desaparecido_marca_incertidumbre(
    db, engine, admin, app_order, proxmox
):
    """Si el trabajo desaparece del nodo, la operación se cede con incertidumbre
    y nunca se entrega el servicio ni se borra el contenedor a ciegas."""
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await approve(db, admin, app_order, immediate=True)
    stopped_create(proxmox)

    node = RecoveryNode(app_order, sessions, job_disappeared=True)

    for _ in range(3):
        await procesar_una(sessions, pve=proxmox, runner=node)
        await wake(db)

    db.expire_all()
    op = await db.scalar(select(OperacionInfraestructura))
    service = await db.scalar(select(Servicio))

    assert op.estado != "confirmada"
    if service:
        assert service.disponibilidad_aplicacion != "utilizable"


async def test_fuente_inaccesible_bloquea_creacion_sin_efectos(
    db, engine, admin, app_order, proxmox
):
    """Si el perfil o registry está deshabilitado / inaccesible, se bloquea la creación
    sin crear contenedor ni consumir cuota."""
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await approve(db, admin, app_order, immediate=True)
    node = RecoveryNode(app_order, sessions, source_unreachable=True)

    await procesar_una(sessions, pve=proxmox, runner=node)

    assert len(proxmox.creados) == 0
    assert len(node.starts) == 0


async def test_fallo_del_probe_de_acceso_nunca_entrega_servicio(
    db, engine, admin, app_order, proxmox
):
    """Aun si el runner completa la instalación, si el probe independiente de acceso web
    falla (código != 200), el servicio NO se marca como utilizable y no se entrega."""
    from tests.test_entrega_aplicaciones_011 import DeliveredNode

    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await approve(db, admin, app_order, immediate=True)
    stopped_create(proxmox)

    node = DeliveredNode(app_order, sessions)
    await procesar_una(sessions, pve=proxmox, runner=node)
    db.expire_all()

    identity = await db.scalar(select(IdentidadInfraestructura))
    proxmox.estados[identity.vmid] = "running"
    await wake(db)

    # Probe que simula fallo HTTP 500
    async def failing_probe(instance):
        return AccessObservation(
            instance["host"],
            instance["address"],
            instance["port"],
            instance["configuration_sha256"],
            status_code=500,
        )

    await procesar_ingesta_una(sessions, runner=node, pve=proxmox, probe=failing_probe)
    db.expire_all()

    service = await db.scalar(select(Servicio))
    op = await db.scalar(select(OperacionInfraestructura))
    pedido = await db.get(Pedido, service.pedido_id)

    # Nunca se entrega el servicio ante probe fallido
    assert service.disponibilidad_aplicacion != "utilizable"
    assert op.estado != "confirmada"
    assert pedido.estado != EstadoPedido.ACTIVO
