"""La tarea PVE y el recurso observado deciden el resultado, fuera del HTTP."""
from datetime import timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.pedido import EstadoPedido
from app.models.servicio import Servicio
from app.models.operacion_infraestructura import OperacionInfraestructura
from app.models.compromiso_capacidad import CompromisoCapacidad
from app.worker import procesar_una
from app.utils.clock import clock
from tests.capacity_helpers import perfil_capacidad  # noqa:F401
from tests.test_operaciones_recuperacion import queued, prepared_guest  # noqa:F401


async def test_la_tarea_pendiente_no_materializa_servicio_antes_del_resultado(
    client, db, engine, proxmox, perfil_capacidad, prepared_guest, catedra, usuario_catedra, template, auth_admin, monkeypatch,
):
    now = clock.now(); monkeypatch.setattr(clock, 'now', lambda:now)
    _, operation_id = await queued(client, db, catedra, usuario_catedra, template, auth_admin)
    proxmox.configure_task('pve1', 'UPID:pve1:task:create', [{'status':'running'}, {'status':'stopped','exitstatus':'OK'}])
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await procesar_una(sessions, pve=proxmox)
    assert await db.scalar(select(Servicio)) is None
    assert proxmox.task_polls and len(proxmox.creados) == 1
    now += timedelta(seconds=3)
    await procesar_una(sessions, pve=proxmox)
    operation = await db.get(OperacionInfraestructura, UUID(operation_id), populate_existing=True)
    assert operation.estado == 'confirmada'
    assert (await db.scalar(select(Servicio))).disponibilidad_aplicacion == 'no_verificada'


async def test_si_la_tarea_falla_no_queda_un_servicio_fantasma(
    client, db, engine, proxmox, perfil_capacidad, prepared_guest, catedra, usuario_catedra, template, auth_admin,
):
    pedido, operation_id = await queued(client, db, catedra, usuario_catedra, template, auth_admin)
    proxmox.configure_task('pve1', 'UPID:pve1:task:create', [{'status':'stopped','exitstatus':'volume does not exist'}])
    await procesar_una(async_sessionmaker(engine, expire_on_commit=False), pve=proxmox)
    assert await db.scalar(select(Servicio)) is None
    await db.refresh(pedido)
    operation = await db.get(OperacionInfraestructura, UUID(operation_id), populate_existing=True)
    assert pedido.estado == EstadoPedido.ERROR and operation.estado == 'fallida'
    assert operation.error_codigo == 'tarea_fallida'
    # El doble dejó un recurso parcial: no se presume ausencia ni se libera disco.
    ledger = await db.scalar(select(CompromisoCapacidad))
    assert ledger.estado == 'incierto' and ledger.disk_bytes_retenidos > 0


async def test_fallo_de_consulta_conserva_incertidumbre_y_no_inventa_error_terminal(
    client, db, engine, proxmox, perfil_capacidad, prepared_guest, catedra, usuario_catedra, template, auth_admin,
):
    pedido, operation_id = await queued(client, db, catedra, usuario_catedra, template, auth_admin)
    proxmox.configure_task('pve1', 'UPID:pve1:task:create', [RuntimeError('transporte no observable')])
    await procesar_una(async_sessionmaker(engine, expire_on_commit=False), pve=proxmox)
    await db.refresh(pedido)
    operation = await db.get(OperacionInfraestructura, UUID(operation_id), populate_existing=True)
    assert operation.estado == 'incierta' and operation.upid is not None
    assert pedido.estado == EstadoPedido.EN_DESPLIEGUE and await db.scalar(select(Servicio)) is None
    assert (await db.scalar(select(CompromisoCapacidad))).disk_bytes_retenidos > 0


async def test_las_advertencias_no_son_un_fallo_si_el_recurso_confirma_resultado(
    client, db, engine, proxmox, perfil_capacidad, prepared_guest, catedra, usuario_catedra, template, auth_admin,
):
    _, operation_id = await queued(client, db, catedra, usuario_catedra, template, auth_admin)
    proxmox.configure_task('pve1', 'UPID:pve1:task:create', [{'status':'stopped','exitstatus':'WARNINGS: 1'}])
    await procesar_una(async_sessionmaker(engine, expire_on_commit=False), pve=proxmox)
    operation = await db.get(OperacionInfraestructura, UUID(operation_id), populate_existing=True)
    assert operation.estado == 'confirmada' and len(proxmox.creados) == 1
    assert (await db.scalar(select(Servicio))).disponibilidad_aplicacion == 'no_verificada'
