import asyncio

from fastapi import HTTPException
from sqlalchemy import select,func

from app.models.bitacora_cierre import BitacoraCierre
from app.models.usuario import Usuario
from app.models.vigencia import VigenciaAutorizada
from app.schemas.regularizacion import ConfirmarRegularizacion
from app.services.regularizacion_service import evaluar,confirmar
from tests.capacity_helpers import perfil_capacidad  # noqa:F401
from tests.test_regularizacion_legacy_009 import prepared,decision


async def test_two_admin_decisions_cannot_duplicate_period_or_journal(
    pg_sessions,db,proxmox,perfil_capacidad,catedra,usuario_catedra,template,admin,
):
    service,_=await prepared(db,proxmox,catedra,usuario_catedra,template)
    service_id,admin_id=service.id,admin.id
    preview=await evaluar(db,service_id,actor=admin,pve=proxmox)
    body=ConfirmarRegularizacion(**decision(preview));await db.rollback()
    async def run(key):
        async with pg_sessions() as session:
            actor=await session.get(Usuario,admin_id)
            try:
                result=await confirmar(session,service_id,actor=actor,body=body,clave=key,pve=proxmox)
                await session.commit();return result.status_code
            except HTTPException as exc:
                await session.rollback()
                assert exc.status_code==409
                return exc.status_code
    results=await asyncio.gather(run('concurrent-a'),run('concurrent-b'))
    assert sorted(results)==[200,409]
    async with pg_sessions() as session:
        assert await session.scalar(select(func.count()).select_from(BitacoraCierre))==1
        assert await session.scalar(select(func.count()).select_from(VigenciaAutorizada))==1
