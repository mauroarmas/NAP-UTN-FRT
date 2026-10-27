"""One real race for the new branch; no repeated matrix or real PVE effects."""
import asyncio

from fastapi import HTTPException
from sqlalchemy import select,func

from app.models.compromiso_capacidad import CompromisoCapacidad
from app.models.pedido import EstadoPedido,ModeloServicio
from app.services import evaluacion_service,admision_service
from tests import factories
from tests.test_admision_aplicaciones_011 import app_order
from tests.capacity_helpers import perfil_capacidad
from tests.test_reserva_red_aplicacion_011 import red_aplicaciones_011
from infra.applications.tests.conftest import profile_entry


async def test_two_app_approvals_cannot_reserve_the_same_remaining_capacity(db,pg_sessions,admin,
        app_order,proxmox,catedra,usuario_catedra):
    app=app_order
    proxmox.nodos[0]['maxcpu']=3  # Margin 1: exactly one Medium can be approved.
    other=await factories.crear_pedido(db,catedra.id,usuario_catedra.id,app.template.id,
        estado=EstadoPedido.SOLICITADO,modelo_servicio=ModeloServicio.SAAS)
    ids=[app.pedido.id,other.id]
    evaluations=[await evaluacion_service.evaluar(db,pedido_id,actor=admin,payload=app.body) for pedido_id in ids]
    await db.commit();barrier=asyncio.Barrier(2)
    async def decide(index):
        async with pg_sessions() as session:
            await barrier.wait()
            try:
                result=await admision_service.aprobar(session,ids[index],actor=admin,
                    payload={**app.body,'capacidad_token':evaluations[index]['capacidad_token']},clave=f'app-race-{index}')
                await session.commit();return result.status_code
            except HTTPException as error:
                await session.rollback();return error.status_code
    results=await asyncio.wait_for(asyncio.gather(decide(0),decide(1)),timeout=15)
    assert sorted(results)==[200,409]
    assert await db.scalar(select(func.count()).select_from(CompromisoCapacidad))==1
    assert not proxmox.creados
