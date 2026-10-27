"""El pool de red comparte la exclusión real de las decisiones de capacidad."""
import asyncio
from uuid import uuid4
import pytest
from app.config import get_settings
from app.services.identidad_infra_service import reclamar
from tests.test_reserva_red_009 import new_operation
from tests.capacity_helpers import perfil_capacidad  # noqa: F401


@pytest.mark.postgres
async def test_dos_reclamaciones_no_comparten_destino_preparado(pg_sessions,proxmox,monkeypatch):
    from sqlalchemy import select, func
    from app.models.identidad_infraestructura import IdentidadInfraestructura
    settings=get_settings()
    monkeypatch.setattr(settings,'infrastructure_profile',{'cluster_id':str(uuid4()),'nodos':{'pve1':{}}})
    keys=[str(uuid4()),str(uuid4())]
    slots={key:{'host':f'pg{i}.example.edu','address':f'10.20.0.{i+10}',
        'mac_address':f'02:00:00:00:00:{i+10:02x}','products':['postgresql']} for i,key in enumerate(keys)}
    monkeypatch.setattr(settings,'network_profiles',{'red':{'instances':slots,'nodes':['pve1'],'bridge':'vmbr0',
        'allowed_cidrs':['10.20.0.0/24'],'client_cidrs':['10.30.0.0/24']}})
    barrier=asyncio.Barrier(2)
    async def claim():
        async with pg_sessions() as db:
            operation=await new_operation(db)
            await db.commit()
            await barrier.wait()
            identity=await reclamar(db,operation,pve=proxmox)
            await db.commit()
            return str(identity.resource_uuid)
    results=await asyncio.wait_for(asyncio.gather(claim(),claim()),timeout=15)
    assert set(results)==set(keys)
    async with pg_sessions() as db:
        assert await db.scalar(select(func.count()).select_from(IdentidadInfraestructura))==2


@pytest.mark.postgres
async def test_avisos_concurrentes_no_duplican_historia_ni_correos(db,engine,proxmox,perfil_capacidad,
        catedra,usuario_catedra,template,admin):
    from datetime import timedelta
    from zoneinfo import ZoneInfo
    from sqlalchemy import select,func
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.models.vigencia import VigenciaAutorizada
    from app.models.notificacion import Notificacion
    from app.models.servicio_historial import ServicioHistorial
    from app.services.vigencia_service import resolver_fechas
    from app.services.vencimiento_service import aplicar_vencimientos
    from app.utils.clock import clock
    from tests.capacity_helpers import materializado
    service,_=await materializado(db,proxmox,catedra,usuario_catedra,template)
    row=await db.scalar(select(VigenciaAutorizada).where(VigenciaAutorizada.servicio_id==service.id))
    today=clock.now().astimezone(ZoneInfo('America/Argentina/Tucuman')).date()
    dates=resolver_fechas(today,today+timedelta(days=2),'America/Argentina/Tucuman')
    row.inicio_at,row.fin_exclusivo_at=dates.inicio_at,dates.fin_exclusivo_at
    row.desde_local,row.hasta_local=dates.desde,dates.hasta
    await db.commit()
    sessions=async_sessionmaker(engine,expire_on_commit=False)
    barrier=asyncio.Barrier(2)
    async def run():
        async with sessions() as session:
            await barrier.wait()
            return await aplicar_vencimientos(session)
    await asyncio.wait_for(asyncio.gather(run(),run()),timeout=15)
    assert await db.scalar(select(func.count()).select_from(Notificacion))==4
    assert await db.scalar(select(func.count()).select_from(ServicioHistorial))==1
