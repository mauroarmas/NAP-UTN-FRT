import asyncio
from copy import deepcopy

from fastapi import HTTPException
from sqlalchemy import select,func
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.bitacora_cierre import BitacoraCierre
from app.services.backfill_cierre_service import planificar,aplicar
from tests.test_backfill_cierre_009 import legacy


async def test_two_real_sessions_do_not_duplicate_migration_or_quarantine(engine,db,catedra,usuario_catedra,template):
    await legacy(db,catedra,usuario_catedra,template)
    plan=await planificar(db)
    await db.rollback()
    sessions=async_sessionmaker(engine,expire_on_commit=False)
    async def run():
        async with sessions() as session:
            try:
                result=await aplicar(session,deepcopy(plan),operador='operador-fixture',referencia='copia-prueba')
                await session.commit();return result['aplicados']
            except HTTPException as exc:
                await session.rollback()
                assert exc.status_code==409 and exc.detail['codigo']=='plan_desactualizado'
                return 'plan_desactualizado'
    results=await asyncio.gather(run(),run())
    assert results.count(2)==1 and results.count('plan_desactualizado')==1
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(BitacoraCierre))==2
