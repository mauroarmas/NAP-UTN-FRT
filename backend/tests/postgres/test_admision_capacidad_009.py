import asyncio

from fastapi import HTTPException
import pytest
from sqlalchemy import select, func

from app.models.usuario import Usuario
from app.models.compromiso_capacidad import CompromisoCapacidad
from app.models.pedido import Pedido, PedidoHistorial
from tests.capacity_helpers import perfil_capacidad, seleccion, preparar_pedido
from tests.capacity_helpers import materializado


@pytest.mark.parametrize('repetition', range(10))
@pytest.mark.parametrize('same_request', [False, True])
async def test_only_one_approval_for_one_remaining_assignment(db, pg_sessions, proxmox, perfil_capacidad, admin, catedra, usuario_catedra, template, repetition, same_request):
    from app.services.evaluacion_service import evaluar
    from app.services.admision_service import aprobar
    template.default_vcpus = 7  # 8 - margen anfitrión 1: saldo de una asignación.
    first = await preparar_pedido(db, catedra, usuario_catedra, template)
    second = first if same_request else await preparar_pedido(db, catedra, usuario_catedra, template)
    payload = seleccion(template)
    evaluations = [await evaluar(db, row.id, actor=admin, payload=payload, pve=proxmox) for row in [first, second]]
    ids, actor_id = [first.id, second.id], admin.id
    await db.commit()
    barrier = asyncio.Barrier(2)

    async def admit(index):
        async with pg_sessions() as session:
            actor = await session.get(Usuario, actor_id)
            await barrier.wait()
            try:
                result = await aprobar(session, ids[index], actor=actor,
                    payload={**evaluations[index]['seleccion'], 'capacidad_token': evaluations[index]['capacidad_token']},
                    clave=f'approve-{repetition}-{index}', pve=proxmox)
                await session.commit()
                return result.status_code
            except HTTPException as exc:
                await session.rollback()
                return exc.status_code
    assert sorted(await asyncio.gather(admit(0), admit(1))) == [200, 409]
    async with pg_sessions() as session:
        assert await session.scalar(select(func.count()).select_from(CompromisoCapacidad)) == 1
        assert await session.scalar(select(func.count()).select_from(PedidoHistorial).where(PedidoHistorial.estado_nuevo == 'aprobado')) == 1


@pytest.mark.parametrize('repetition', range(10))
async def test_revert_and_expire_compete_with_approval_without_double_release(db, pg_sessions, proxmox, perfil_capacidad, admin, catedra, usuario_catedra, template, monkeypatch, repetition):
    from datetime import timedelta
    from app.services.evaluacion_service import evaluar
    from app.services.admision_service import aprobar, liberar
    from app.utils.clock import clock
    now = clock.now()
    monkeypatch.setattr(clock, 'now', lambda: now)
    pedido = await preparar_pedido(db, catedra, usuario_catedra, template)
    evaluation = await evaluar(db, pedido.id, actor=admin, payload=seleccion(template), pve=proxmox)
    payload = {**evaluation['seleccion'], 'capacidad_token': evaluation['capacidad_token']}
    await aprobar(db, pedido.id, actor=admin, payload=payload, clave='initial-approval', pve=proxmox)
    await db.commit()
    identity, actor_id = pedido.id, admin.id
    now += timedelta(days=2)
    barrier = asyncio.Barrier(3)

    async def decide(kind):
        async with pg_sessions() as session:
            actor = await session.get(Usuario, actor_id)
            await barrier.wait()
            try:
                if kind == 'approve':
                    result = await aprobar(session, identity, actor=actor, payload=payload, clave='second-approval', pve=proxmox)
                else:
                    result = await liberar(session, identity, actor=None if kind == 'expire' else actor,
                        motivo='Reserva vencida' if kind == 'expire' else 'Reversión administrativa', expirar=kind == 'expire', clave=kind)
                await session.commit()
                return result.status_code
            except HTTPException as exc:
                await session.rollback()
                return exc.status_code
    results = await asyncio.gather(*(decide(kind) for kind in ['approve', 'revert', 'expire']))
    assert results.count(200) == 1
    async with pg_sessions() as session:
        ledger = await session.scalar(select(CompromisoCapacidad))
        assert ledger.estado == 'liberado' and ledger.vcpus_retenidos == ledger.ram_mb_retenida == ledger.disk_bytes_retenidos == 0
        history = (await session.scalars(select(PedidoHistorial).where(PedidoHistorial.pedido_id == identity))).all()
        assert len([entry for entry in history if entry.estado_anterior == 'aprobado']) == 1


@pytest.mark.parametrize('repetition', range(10))
async def test_two_starts_compete_for_one_assignment(db, pg_sessions, proxmox, perfil_capacidad, admin, catedra, usuario_catedra, template, repetition):
    from app.services.admision_service import iniciar
    first, first_ledger = await materializado(db, proxmox, catedra, usuario_catedra, template, vmid=100, vcpus=7)
    second, second_ledger = await materializado(db, proxmox, catedra, usuario_catedra, template, vmid=101, vcpus=7)
    ids, actor_id = [first.id, second.id], admin.id
    barrier = asyncio.Barrier(2)
    async def start(index):
        async with pg_sessions() as session:
            actor = await session.get(Usuario, actor_id)
            await barrier.wait()
            try:
                result = await iniciar(session, ids[index], actor=actor, clave=f'start-{repetition}-{index}', pve=proxmox)
                await session.commit()
                return result.status_code
            except HTTPException as exc:
                await session.rollback()
                assert exc.detail['codigo'] == 'sin_capacidad'
                return exc.status_code
    assert sorted(await asyncio.gather(start(0), start(1))) == [202, 409]
    async with pg_sessions() as session:
        ledgers = (await session.scalars(select(CompromisoCapacidad))).all()
        assert sorted(row.vcpus_retenidos for row in ledgers) == [0, 7]
        assert all(row.disk_bytes_retenidos == 10 * 1024**3 for row in ledgers)


@pytest.mark.parametrize('repetition', range(10))
async def test_approval_and_start_use_the_same_capacity_lock(db, pg_sessions, proxmox, perfil_capacidad, admin, catedra, usuario_catedra, template, repetition):
    from app.services.admision_service import iniciar, aprobar
    from app.services.evaluacion_service import evaluar
    service, _ = await materializado(db, proxmox, catedra, usuario_catedra, template, vcpus=7)
    pedido = await preparar_pedido(db, catedra, usuario_catedra, template)
    selected = seleccion(template)
    selected['asignacion']['vcpus'] = 7
    evaluation = await evaluar(db, pedido.id, actor=admin, payload=selected, pve=proxmox)
    payload = {**evaluation['seleccion'], 'capacidad_token': evaluation['capacidad_token']}
    actor_id, service_id, request_id = admin.id, service.id, pedido.id
    await db.commit()
    barrier = asyncio.Barrier(2)
    async def execute(start):
        async with pg_sessions() as session:
            actor = await session.get(Usuario, actor_id)
            await barrier.wait()
            try:
                if start:
                    result = await iniciar(session, service_id, actor=actor, clave='mixed-start', pve=proxmox)
                else:
                    result = await aprobar(session, request_id, actor=actor, payload=payload, clave='mixed-approval', pve=proxmox)
                await session.commit()
                return result.status_code
            except HTTPException as exc:
                await session.rollback()
                return exc.status_code
    results = await asyncio.gather(execute(True), execute(False))
    assert results.count(409) == 1
    assert sum(value in {200, 202} for value in results) == 1
    async with pg_sessions() as session:
        assert await session.scalar(select(func.sum(CompromisoCapacidad.vcpus_retenidos))) == 7
