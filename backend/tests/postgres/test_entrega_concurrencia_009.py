import asyncio

from sqlalchemy import select, func

from app.models.evento_seguridad import EventoSeguridad
from app.models.notificacion import Notificacion
from app.models.pedido import Pedido, PedidoHistorial
from app.models.servicio_historial import ServicioHistorial
from app.models.usuario import Usuario
from app.services.verificacion_acceso_service import verificar
from tests.test_entrega_acceso_009 import prepared_access
from tests.test_evidencias_009 import evidence_definition, prepared_instance_document


async def test_two_real_transactions_deliver_and_notify_once(client, db, pg_sessions,
        prepared_access, auth_admin, admin):
    service_id, document = prepared_access
    response = await client.post('/evidencias', json=document, headers=auth_admin | {'Idempotency-Key': 'pg-access-proof'})
    assert response.status_code == 201, response.text
    body = {'evidencia_ref': response.json()['evidencia_ref'], 'endpoint': document['resultado']['endpoint'],
        'observado_at': document['observado_at']}
    actor_id = admin.id
    await db.commit()
    barrier = asyncio.Barrier(2)
    async def deliver(key):
        async with pg_sessions() as session:
            actor = await session.get(Usuario, actor_id)
            await barrier.wait()
            result = await verificar(session, actor=actor, servicio_id=service_id, body=body, clave=key)
            await session.commit()
            return result.status_code
    results = await asyncio.wait_for(asyncio.gather(deliver('pg-deliver-a'), deliver('pg-deliver-b')), timeout=8)
    assert results == [200, 200]
    assert await db.scalar(select(func.count()).select_from(Notificacion).where(
        Notificacion.servicio_id == service_id, Notificacion.canal == 'portal')) == 1
    assert await db.scalar(select(func.count()).select_from(EventoSeguridad).where(
        EventoSeguridad.accion == 'verificar_acceso_servicio')) == 1
    assert await db.scalar(select(func.count()).select_from(ServicioHistorial).where(
        ServicioHistorial.servicio_id == service_id)) == 1
    assert await db.scalar(select(func.count()).select_from(PedidoHistorial).where(
        PedidoHistorial.estado_nuevo == 'activo')) == 1
