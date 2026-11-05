"""Concurrencia real del cupo de terminales (feature 022): sólo tiene sentido con el bloqueo de fila de PostgreSQL."""
import asyncio

from sqlalchemy import select

from app.models.sesion_terminal import SesionTerminal
from app.services import terminal_sesiones_service as ts
from tests import factories


async def test_aperturas_simultaneas_de_la_misma_persona_no_superan_el_cupo(db, pg_sessions, catedra, usuario_catedra, template):
    servicio = await factories.crear_servicio(db, catedra.id, template.id, proxmox_vmid='101')
    persona, servicio_id = usuario_catedra.id, servicio.id
    barrera = asyncio.Barrier(5)

    async def abrir():
        await barrera.wait()
        try:
            return await ts.abrir(pg_sessions, usuario_id=persona, servicio_id=servicio_id, nodo='pve1', limite=2)
        except Exception as exc:
            return exc

    resultados = await asyncio.gather(*(abrir() for _ in range(5)))
    exitos = [r for r in resultados if not isinstance(r, Exception)]
    rechazos = [r for r in resultados if isinstance(r, Exception)]
    assert len(exitos) == 2 and len(rechazos) == 3
    assert all(getattr(r, 'status_code', None) == 429 for r in rechazos)
    async with pg_sessions() as s:
        abiertas = (await s.scalars(select(SesionTerminal).where(SesionTerminal.cerrada_at.is_(None)))).all()
    assert len(abiertas) == 2


async def test_el_cupo_es_por_persona(db, pg_sessions, catedra, usuario_catedra, admin, template):
    servicio = await factories.crear_servicio(db, catedra.id, template.id, proxmox_vmid='101')
    persona, otra, servicio_id = usuario_catedra.id, admin.id, servicio.id
    await ts.abrir(pg_sessions, usuario_id=persona, servicio_id=servicio_id, nodo='pve1', limite=1)
    assert await ts.abrir(pg_sessions, usuario_id=otra, servicio_id=servicio_id, nodo='pve1', limite=1)
