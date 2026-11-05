import pytest
from sqlalchemy import func, select

from app.models.pedido import EstadoPedido, Pedido, PedidoHistorial
from app.models.usuario import Usuario
from app.services import historial_service, pedido_service
from tests.factories import crear_pedido


async def test_repeated_event_is_one_transition_and_one_history(db, catedra, admin, template):
    pedido = await crear_pedido(db, catedra.id, admin.id, template.id, estado=EstadoPedido.SOLICITADO)
    for _ in range(2):
        await pedido_service.transicionar(db, pedido.id, EstadoPedido.REQUIERE_AJUSTE,
                                         usuario=admin, motivo='Aclarar necesidad', evento_clave='adjustment:1')
    await db.commit()
    entries = (await db.scalars(select(PedidoHistorial).where(PedidoHistorial.pedido_id == pedido.id))).all()
    assert len(entries) == 1
    assert entries[0].actor_tipo == 'usuario'
    assert entries[0].usuario_id == admin.id


async def test_system_author_is_explicit_and_history_is_append_only(db, catedra, admin, template):
    pedido = await crear_pedido(db, catedra.id, admin.id, template.id)
    entry = historial_service.registrar_pedido(pedido.id, 'aprobado', 'en_despliegue', comentario='Sistema')
    db.add(entry)
    await db.commit()
    assert entry.actor_tipo == 'sistema' and entry.usuario_id is None
    entry.comentario = 'sobrescribir historia'
    with pytest.raises(ValueError, match='historial'):
        await db.flush()
    await db.rollback()


async def test_transition_failure_rolls_back_state_and_history(db, catedra, admin, template):
    pedido = await crear_pedido(db, catedra.id, admin.id, template.id, estado=EstadoPedido.SOLICITADO)
    pedido_id, admin_id = pedido.id, admin.id
    await db.rollback()
    with pytest.raises(RuntimeError):
        async with db.begin():
            actor = await db.get(Usuario, admin_id)
            await pedido_service.transicionar(db, pedido_id, EstadoPedido.REQUIERE_AJUSTE,
                                             usuario=actor, motivo='Cambio incompleto', evento_clave='rollback:1')
            raise RuntimeError('Simular fallo antes del commit')
    stored = await db.get(Pedido, pedido_id)
    assert stored.estado == EstadoPedido.SOLICITADO
    assert await db.scalar(select(func.count()).select_from(PedidoHistorial).where(PedidoHistorial.pedido_id == pedido_id)) == 0
