"""Sesiones de la terminal web: cupo, huérfanas, cierres pedidos, arranque y auditoría (feature 022)."""
import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.evento_seguridad import EventoSeguridad
from app.models.servicio import EstadoServicio
from app.models.sesion_terminal import SesionTerminal
from app.services import terminal_sesiones_service as ts
from app.utils.clock import clock
from tests import factories


@pytest.fixture
def sessions(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


async def _servicio(db, catedra, template):
    return await factories.crear_servicio(db, catedra.id, template.id, proxmox_vmid='101')


async def test_el_cupo_se_respeta_y_se_libera_al_cerrar(db, sessions, catedra, usuario_catedra, template):
    servicio = await _servicio(db, catedra, template)
    ids = [await ts.abrir(sessions, usuario_id=usuario_catedra.id, servicio_id=servicio.id, nodo='pve1', limite=2) for _ in range(2)]
    with pytest.raises(Exception) as exc:
        await ts.abrir(sessions, usuario_id=usuario_catedra.id, servicio_id=servicio.id, nodo='pve1', limite=2)
    assert exc.value.status_code == 429 and exc.value.detail['codigo'] == 'limite_sesiones'
    assert await ts.cerrar(sessions, ids[0], 'persona') is not None
    assert await ts.abrir(sessions, usuario_id=usuario_catedra.id, servicio_id=servicio.id, nodo='pve1', limite=2)


async def test_cerrar_es_idempotente_y_audita_una_sola_vez(db, sessions, catedra, usuario_catedra, template):
    servicio = await _servicio(db, catedra, template)
    sid = await ts.abrir(sessions, usuario_id=usuario_catedra.id, servicio_id=servicio.id, nodo='pve1', limite=3)
    assert await ts.cerrar(sessions, sid, 'persona') is not None
    assert await ts.cerrar(sessions, sid, 'error') is None
    eventos = (await db.scalars(select(EventoSeguridad).where(EventoSeguridad.accion == 'terminal_cerrada'))).all()
    assert len(eventos) == 1 and 'persona' in eventos[0].motivo


async def test_las_sesiones_huerfanas_liberan_el_cupo(db, sessions, catedra, usuario_catedra, template):
    servicio = await _servicio(db, catedra, template)
    huerfana = await ts.abrir(sessions, usuario_id=usuario_catedra.id, servicio_id=servicio.id, nodo='pve1', limite=1)
    fila = await db.get(SesionTerminal, huerfana)
    fila.ultimo_latido_at = clock.now() - timedelta(seconds=ts.LATIDO_VIGENTE_SEGUNDOS + 30)
    await db.commit()
    nueva = await ts.abrir(sessions, usuario_id=usuario_catedra.id, servicio_id=servicio.id, nodo='pve1', limite=1)
    await db.refresh(fila)
    assert nueva != huerfana and fila.motivo_cierre == 'error' and fila.cerrada_at is not None


async def test_el_latido_actualiza_la_ultima_entrada_solo_si_se_indica(db, sessions, catedra, usuario_catedra, template):
    servicio = await _servicio(db, catedra, template)
    sid = await ts.abrir(sessions, usuario_id=usuario_catedra.id, servicio_id=servicio.id, nodo='pve1', limite=3)
    fila = await db.get(SesionTerminal, sid)
    antes = fila.ultima_entrada_at
    await ts.latido(sessions, sid)
    await db.refresh(fila)
    assert fila.ultima_entrada_at == antes
    nueva = clock.now() + timedelta(minutes=1)
    await ts.latido(sessions, sid, ultima_entrada=nueva)
    await db.refresh(fila)
    assert fila.ultima_entrada_at is not None and fila.ultima_entrada_at != antes


async def test_solicitar_cierre_por_persona_servicio_o_catedra(db, sessions, catedra, usuario_catedra, template):
    s1 = await _servicio(db, catedra, template)
    otra = await factories.crear_catedra(db, nombre='Otra')
    s2 = await factories.crear_servicio(db, otra.id, template.id, proxmox_vmid='202')
    a = await ts.abrir(sessions, usuario_id=usuario_catedra.id, servicio_id=s1.id, nodo='pve1', limite=5)
    b = await ts.abrir(sessions, usuario_id=usuario_catedra.id, servicio_id=s2.id, nodo='pve1', limite=5)
    async with sessions() as s, s.begin():
        assert await ts.solicitar_cierre(s, motivo='retiro', usuario_id=usuario_catedra.id, catedra_ids=[otra.id]) == 1
    assert (await ts.consultar(sessions, b))['cierre_solicitado_at'] is not None
    assert (await ts.consultar(sessions, a))['cierre_solicitado_at'] is None
    async with sessions() as s, s.begin():
        assert await ts.solicitar_cierre(s, motivo='baja', servicio_id=s1.id) == 1
        assert await ts.solicitar_cierre(s, motivo='baja', servicio_id=s1.id) == 0        # ya pedido: no se repite


async def test_al_arrancar_el_portal_se_cierran_las_sesiones_abiertas(db, sessions, catedra, usuario_catedra, template):
    servicio = await _servicio(db, catedra, template)
    for _ in range(2):
        await ts.abrir(sessions, usuario_id=usuario_catedra.id, servicio_id=servicio.id, nodo='pve1', limite=5)
    assert await ts.cerrar_abiertas_al_arrancar(sessions) == 2
    filas = (await db.scalars(select(SesionTerminal).execution_options(populate_existing=True))).all()
    assert {f.motivo_cierre for f in filas} == {'reinicio_portal'} and all(f.cerrada_at for f in filas)
    assert await ts.cerrar_abiertas_al_arrancar(sessions) == 0


async def test_administracion_ve_y_cierra_sesiones_sin_contenido(client, db, sessions, catedra, usuario_catedra, template, auth_admin, auth_catedra):
    servicio = await _servicio(db, catedra, template)
    sid = await ts.abrir(sessions, usuario_id=usuario_catedra.id, servicio_id=servicio.id, nodo='pve1', limite=5)
    assert (await client.get('/admin/sesiones-terminal', headers=auth_catedra)).status_code == 403
    r = await client.get('/admin/sesiones-terminal', headers=auth_admin)
    [fila] = r.json()
    assert set(fila) == {'id', 'usuario_id', 'servicio_id', 'nodo', 'abierta_at', 'ultima_entrada_at'}
    c = await client.post(f'/admin/sesiones-terminal/{sid}/cerrar', headers=auth_admin | {'Idempotency-Key': 'k1'})
    assert c.status_code == 202
    assert (await ts.consultar(sessions, sid))['motivo_solicitud'] == 'administracion'
    assert (await client.post('/admin/sesiones-terminal/no-es-uuid/cerrar', headers=auth_admin | {'Idempotency-Key': 'k2'})).status_code == 404
