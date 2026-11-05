import asyncio
from sqlalchemy import select,func

from app.models.usuario import Usuario
from app.models.ensayo_preparacion import EnsayoPreparacion
from app.models.compromiso_capacidad import CompromisoCapacidad
from app.services import preparacion_simple_service as simple
from tests.test_preparacion_simple import setup
from tests.capacity_helpers import perfil_capacidad  # noqa: F401


async def test_dos_altas_simultaneas_comparten_preparacion_y_reservas(db,admin,proxmox,perfil_capacidad,monkeypatch,pg_sessions):
    inc,_,builder=await setup(db,admin,proxmox,monkeypatch,perfil_capacidad)
    admin_id=admin.id
    async def start(key):
        async with pg_sessions() as session:
            actor=await session.get(Usuario,admin_id)
            result=await simple.preparar(session,inc,actor=actor,clave=key,pve=proxmox,builder=builder)
            await session.commit()
            return result.resultado['preparacion_id']
    first,second=await asyncio.gather(start('primer-click'),start('segundo-click'))
    assert first==second
    assert await db.scalar(select(func.count()).select_from(EnsayoPreparacion))==1
    assert await db.scalar(select(func.count()).select_from(CompromisoCapacidad).where(CompromisoCapacidad.recurso_ensayo_id.is_not(None)))==2
    trial=await db.scalar(select(EnsayoPreparacion))
    assert trial.expires_at is None and trial.aviso_at is None
    assert len(builder.calls)==1
