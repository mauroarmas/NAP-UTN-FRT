"""Fotos obsoletas y contabilidad entre sesiones; exclusión real en tests/postgres."""
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy import select, func

from app.models.pedido import EstadoPedido
from app.models.compromiso_capacidad import CompromisoCapacidad
from app.services import capacidad_service, evaluacion_service, admision_service
from tests import factories
from tests.capacity_helpers import perfil_capacidad, seleccion, evaluar_http, aprobar_http  # noqa:F401
from tests.test_operaciones_recuperacion import prepared_guest  # noqa:F401


async def _dos_pedidos(db, catedra, usuario, template):
    return tuple([await factories.crear_pedido(db, catedra.id, usuario.id, template.id,
        estado=EstadoPedido.SOLICITADO) for _ in range(2)])


async def test_dos_admins_con_fotos_iguales_solo_el_token_actual_aprueba(
    client, db, catedra, usuario_catedra, template, auth_admin, perfil_capacidad,
):
    uno, dos = await _dos_pedidos(db, catedra, usuario_catedra, template)
    first, ev_first = await evaluar_http(client, uno, template, auth_admin)
    second, ev_second = await evaluar_http(client, dos, template, auth_admin)
    second_id = dos.id
    assert ev_first['libre_antes'] == ev_second['libre_antes']
    # El token se liga también al pedido: no se comparte entre intenciones.
    assert first['capacidad_token'] != second['capacidad_token']
    primera = await client.post(f'/pedidos/{uno.id}/aprobar', json=first,
        headers=auth_admin | {'Idempotency-Key':'first-capacity'})
    segunda = await client.post(f'/pedidos/{second_id}/aprobar', json=second,
        headers=auth_admin | {'Idempotency-Key':'stale-capacity'})
    assert primera.status_code == 200, primera.text
    assert segunda.status_code == 409 and segunda.json()['detail']['codigo'] == 'evaluacion_desactualizada'


async def test_aprobaciones_en_sesiones_distintas_no_pierden_reserva(
    engine, db, catedra, usuario_catedra, template, admin, proxmox, perfil_capacidad,
):
    uno, dos = await _dos_pedidos(db, catedra, usuario_catedra, template)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    ids = [uno.id, dos.id]
    payload = seleccion(template)
    # SQLite no demuestra paralelismo: confirmar secuencialmente en sesiones
    # distintas y comprobar el ledger. La carrera de 4001 se prueba en PostgreSQL.
    for request_id in ids:
        async with sessions() as session:
            evaluation = await evaluacion_service.evaluar(session, request_id, actor=admin, payload=payload, pve=proxmox)
            await admision_service.aprobar(session, request_id, actor=admin,
                payload=payload | {'capacidad_token':evaluation['capacidad_token']}, clave=f'independent-{request_id}', pve=proxmox)
            await session.commit()
    state = await capacidad_service.panorama(db, pve=proxmox)
    assert state['reservado']['vcpus'] == 2 * template.default_vcpus
    assert await db.scalar(select(func.count()).select_from(CompromisoCapacidad)) == 2


async def test_la_reserva_no_se_cuenta_dos_veces_al_desplegar(
    client, db, engine, catedra, usuario_catedra, template, auth_admin, perfil_capacidad, prepared_guest, proxmox,
):
    from app.worker import procesar_una
    pedido = await factories.crear_pedido(db, catedra.id, usuario_catedra.id, template.id, estado=EstadoPedido.SOLICITADO)
    response = await aprobar_http(client, pedido, template, auth_admin)
    assert response.status_code == 200, response.text
    before = await capacidad_service.panorama(db)
    response = await client.post(f'/servicios/desplegar/{pedido.id}', json={},
        headers=auth_admin | {'Idempotency-Key':'one-contribution'})
    assert response.status_code == 202, response.text
    await procesar_una(async_sessionmaker(engine, expire_on_commit=False), pve=proxmox)
    after = await capacidad_service.panorama(db)
    assert after['reservado']['vcpus'] == 0
    assert after['desplegado']['vcpus'] == template.default_vcpus
    assert after['comprometido']['vcpus'] == before['comprometido']['vcpus']
    assert await db.scalar(select(func.count()).select_from(CompromisoCapacidad)) == 1
