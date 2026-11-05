"""One actual PostgreSQL race; registry responses are bounded test fixtures."""
import asyncio

from sqlalchemy import select,func

from app.models.usuario import Usuario
from app.models.configuracion_despliegue import ConfiguracionDespliegue
from app.models.recurso_template import RecursoTemplate
from app.models.compromiso_capacidad import CompromisoCapacidad
from app.services import configuracion_despliegue_service as catalog
from tests.test_templates_aplicaciones_011 import (catalog_image,request_body,app_order,approve,
    perfil_capacidad,red_aplicaciones_011,profile_entry)


async def test_parallel_same_key_creates_one_offer_and_never_reserves(db,pg_sessions,admin,app_order,catalog_image):
    admin_id=admin.id;calls,resolver=catalog_image
    entered=0;ready=asyncio.Event()
    async def metadata(*args,**kwargs):
        nonlocal entered
        entered+=1
        if entered==2:ready.set()
        await ready.wait()
        return await resolver(*args,**kwargs)
    async def request():
        async with pg_sessions() as session:
            actor=await session.get(Usuario,admin_id)
            result=await catalog.change(session,actor=actor,body=request_body(),clave='parallel-image',resolver=metadata)
            await session.commit();return result
    results=await asyncio.wait_for(asyncio.gather(request(),request()),timeout=15)
    assert results[0].resultado==results[1].resultado
    assert sorted(r.replayed for r in results)==[False,True]
    assert await db.scalar(select(func.count()).select_from(RecursoTemplate).where(RecursoTemplate.nombre=='Campus propio'))==1
    assert await db.scalar(select(func.count()).select_from(CompromisoCapacidad))==0
