"""Reconciliador de identidades individuales de consola (feature 022). Dobles del nodo; no prueban Proxmox real."""
import logging

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import get_settings
from app.models.catedra import Catedra
from app.models.identidad_consola import IdentidadConsola
from app.models.usuario import RolUsuario
from app.services import identidad_consola_service as svc
from app.utils.secretos import configured_keyring
from tests import factories
from tests.console_identity_helpers import RunnerConsola


@pytest.fixture
def sessions(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
def dos_nodos(monkeypatch):
    from uuid import uuid4
    monkeypatch.setattr(get_settings(), 'runner_nodes', {'pve1': {}, 'pve2': {}}, raising=False)
    perfil = dict(get_settings().infrastructure_profile or {})
    perfil.setdefault('cluster_id', str(uuid4()))
    monkeypatch.setattr(get_settings(), 'infrastructure_profile', perfil, raising=False)


async def fila(db, usuario):
    return await db.scalar(select(IdentidadConsola).where(IdentidadConsola.usuario_id == usuario.id).execution_options(populate_existing=True))


def password_de(fila_):
    return configured_keyring().decrypt(fila_.password_cifrada, context=f'identidad_consola:{fila_.usuario_id}')['password']


async def test_el_alta_crea_la_identidad_sola_con_contrasena_aleatoria_cifrada(db, sessions, catedra, usuario_catedra, caplog):
    caplog.set_level(logging.DEBUG)
    runner = RunnerConsola(pools=[f'catedra-{catedra.id}'])
    assert await svc.reconciliar_usuario(sessions, usuario_catedra.id, runner=runner) == 'lista'
    f = await fila(db, usuario_catedra)
    assert f.identidad == f'nap-u{usuario_catedra.id}@pve' and f.estado == 'lista' and f.pools_aplicados == [f'catedra-{catedra.id}']
    clave = password_de(f)
    assert len(clave) >= 32 and clave not in f.password_cifrada
    assert runner.usuarios[f.identidad]['password'] == clave
    assert clave not in caplog.text
    todo = '\n'.join(map(repr, (await db.execute(text('select * from identidades_consola'))).fetchall()))
    assert clave not in todo


async def test_dos_personas_nunca_comparten_identidad_ni_contrasena(db, sessions, catedra, usuario_catedra):
    otro = await factories.crear_usuario(db, username='otra', rol=RolUsuario.CATEDRA_ADMIN)
    otra_catedra = await factories.crear_catedra(db, nombre='Otra', titular_id=otro.id)
    runner = RunnerConsola(pools=[f'catedra-{catedra.id}', f'catedra-{otra_catedra.id}'])
    await svc.reconciliar_usuario(sessions, usuario_catedra.id, runner=runner)
    await svc.reconciliar_usuario(sessions, otro.id, runner=runner)
    a, b = await fila(db, usuario_catedra), await fila(db, otro)
    assert a.identidad != b.identidad and password_de(a) != password_de(b)
    assert runner.usuarios[a.identidad]['pools'] == {f'catedra-{catedra.id}'}
    assert runner.usuarios[b.identidad]['pools'] == {f'catedra-{otra_catedra.id}'}


async def test_administracion_recibe_todas_las_catedras_activas(db, sessions, admin, catedra):
    otra = await factories.crear_catedra(db, nombre='Otra activa')
    inactiva = await factories.crear_catedra(db, nombre='Inactiva')
    inactiva.activa = False
    await db.commit()
    runner = RunnerConsola(pools=[f'catedra-{catedra.id}', f'catedra-{otra.id}', f'catedra-{inactiva.id}'])
    await svc.reconciliar_usuario(sessions, admin.id, runner=runner)
    assert runner.usuarios[(await fila(db, admin)).identidad]['pools'] == {f'catedra-{catedra.id}', f'catedra-{otra.id}'}


async def test_un_pool_que_todavia_no_existe_queda_pendiente_y_se_completa_despues(db, sessions, catedra, usuario_catedra):
    runner = RunnerConsola(pools=[])
    assert await svc.reconciliar_usuario(sessions, usuario_catedra.id, runner=runner) == 'lista'
    assert (await fila(db, usuario_catedra)).pools_aplicados == []
    runner.pools.add(f'catedra-{catedra.id}')
    from datetime import timedelta
    from app.utils.clock import clock
    (await fila(db, usuario_catedra)).reconciliada_at = clock.now() - timedelta(seconds=svc.REINTENTO_SEGUNDOS + 5)
    await db.commit()
    assert await svc.ciclo(sessions, runner=runner) == {usuario_catedra.id: 'lista'}
    assert (await fila(db, usuario_catedra)).pools_aplicados == [f'catedra-{catedra.id}']


async def test_un_fallo_deja_con_error_y_el_reintento_usa_la_misma_contrasena(db, sessions, catedra, usuario_catedra, caplog):
    caplog.set_level(logging.DEBUG)
    runner = RunnerConsola(pools=[f'catedra-{catedra.id}'])
    runner.falla = {'ensure': 2}   # falla en los dos nodos
    assert await svc.reconciliar_usuario(sessions, usuario_catedra.id, runner=runner) == 'con_error'
    f = await fila(db, usuario_catedra)
    assert f.estado == 'con_error' and f.ultimo_error_seguro == svc.MENSAJE_ERROR and f.pools_aplicados == []
    primera = password_de(f)
    assert await svc.reconciliar_usuario(sessions, usuario_catedra.id, runner=runner) == 'lista'
    f = await fila(db, usuario_catedra)
    assert f.ultimo_error_seguro is None and password_de(f) == primera
    enviadas = {p['password_consola'] for p in runner.acciones('ensure')}
    assert enviadas == {primera}
    assert primera not in caplog.text and primera not in repr(f.ultimo_error_seguro)


async def test_un_fallo_definitivo_del_nodo_tambien_queda_visible(db, sessions, catedra, usuario_catedra):
    runner = RunnerConsola(pools=[f'catedra-{catedra.id}'])
    runner.error_definitivo = 'ROLE_UNAVAILABLE'
    assert await svc.reconciliar_usuario(sessions, usuario_catedra.id, runner=runner) == 'con_error'


async def test_si_un_nodo_no_responde_se_prueba_con_el_otro(db, sessions, catedra, usuario_catedra):
    runner = RunnerConsola(pools=[f'catedra-{catedra.id}'])
    runner.nodos_caidos = {'pve1'}
    assert await svc.reconciliar_usuario(sessions, usuario_catedra.id, runner=runner) == 'lista'
    assert runner.nodos_de('ensure') == ['pve1', 'pve2']


async def test_cambiar_el_titular_retira_a_la_persona_anterior_y_crea_la_nueva(db, sessions, catedra, usuario_catedra, template):
    nuevo = await factories.crear_usuario(db, username='nuevo', rol=RolUsuario.CATEDRA_ADMIN)
    pool = f'catedra-{catedra.id}'
    runner = RunnerConsola(pools=[pool])
    await factories.crear_servicio(db, catedra.id, template.id, proxmox_vmid='101')
    await svc.reconciliar_usuario(sessions, usuario_catedra.id, runner=runner)
    viejo = (await fila(db, usuario_catedra)).identidad
    (await db.get(Catedra, catedra.id)).titular_id = nuevo.id
    await db.commit()
    resumen = await svc.ciclo(sessions, runner=runner)
    assert resumen == {usuario_catedra.id: 'retirada', nuevo.id: 'lista'}
    assert viejo not in runner.usuarios and runner.usuarios[(await fila(db, nuevo)).identidad]['pools'] == {pool}
    assert [101] in runner.terminadas


async def test_retiro_parcial_conserva_la_otra_catedra_y_corta_sesiones_de_la_retirada(db, sessions, catedra, usuario_catedra, template):
    segunda = await factories.crear_catedra(db, nombre='Segunda', titular_id=usuario_catedra.id)
    runner = RunnerConsola(pools=[f'catedra-{catedra.id}', f'catedra-{segunda.id}'])
    await factories.crear_servicio(db, catedra.id, template.id, proxmox_vmid='101')
    await factories.crear_servicio(db, segunda.id, template.id, proxmox_vmid='202')
    await svc.reconciliar_usuario(sessions, usuario_catedra.id, runner=runner)
    (await db.get(Catedra, segunda.id)).titular_id = None
    await db.commit()
    runner.terminadas.clear()
    assert await svc.reconciliar_usuario(sessions, usuario_catedra.id, runner=runner) == 'lista'
    f = await fila(db, usuario_catedra)
    assert f.pools_aplicados == [f'catedra-{catedra.id}'] and runner.usuarios[f.identidad]['pools'] == {f'catedra-{catedra.id}'}
    assert runner.terminadas == [[202], [202]]            # un pedido por nodo, sólo del contenedor de la cátedra retirada
    assert sorted(runner.nodos_de('end_sessions')) == ['pve1', 'pve2']


async def test_retiro_total_elimina_la_cuenta_corta_sesiones_en_todos_los_nodos_y_vuelve_con_contrasena_nueva(
        db, sessions, catedra, usuario_catedra, template):
    runner = RunnerConsola(pools=[f'catedra-{catedra.id}'])
    await factories.crear_servicio(db, catedra.id, template.id, proxmox_vmid='101')
    await svc.reconciliar_usuario(sessions, usuario_catedra.id, runner=runner)
    f = await fila(db, usuario_catedra)
    vieja, ident = password_de(f), f.identidad
    usuario_catedra.activo = False
    await db.commit()
    assert await svc.reconciliar_usuario(sessions, usuario_catedra.id, runner=runner) == 'retirada'
    f = await fila(db, usuario_catedra)
    assert f.estado == 'retirada' and f.pools_aplicados == [] and ident not in runner.usuarios
    assert sorted(runner.nodos_de('end_sessions')) == ['pve1', 'pve2']
    assert await svc.reconciliar_usuario(sessions, usuario_catedra.id, runner=runner) == 'retirada'   # idempotente
    usuario_catedra.activo = True
    await db.commit()
    assert await svc.reconciliar_usuario(sessions, usuario_catedra.id, runner=runner) == 'lista'
    f = await fila(db, usuario_catedra)
    assert f.revision == 2 and password_de(f) != vieja and runner.usuarios[ident]['password'] == password_de(f)


async def test_si_el_retiro_no_se_puede_confirmar_no_queda_marcado_como_retirado(db, sessions, catedra, usuario_catedra):
    runner = RunnerConsola(pools=[f'catedra-{catedra.id}'])
    await svc.reconciliar_usuario(sessions, usuario_catedra.id, runner=runner)
    usuario_catedra.activo = False
    await db.commit()
    runner.falla = {'retire': 5}
    estado = await svc.reconciliar_usuario(sessions, usuario_catedra.id, runner=runner)
    assert estado == 'lista' and (await fila(db, usuario_catedra)).estado == 'lista'     # sigue vigente hasta confirmarlo
    runner.falla = {}
    assert await svc.reconciliar_usuario(sessions, usuario_catedra.id, runner=runner) == 'retirada'


async def test_el_ciclo_no_repite_trabajo_cuando_todo_coincide(db, sessions, catedra, usuario_catedra):
    runner = RunnerConsola(pools=[f'catedra-{catedra.id}'])
    assert await svc.ciclo(sessions, runner=runner) == {usuario_catedra.id: 'lista'}
    n = len(runner.pedidos)
    await db.rollback()
    assert await svc.ciclo(sessions, runner=runner) == {}
    assert len(runner.pedidos) == n


async def test_marcar_para_reintento_toma_la_persona_en_la_proxima_pasada(db, sessions, catedra, usuario_catedra):
    runner = RunnerConsola(pools=[f'catedra-{catedra.id}'])
    runner.falla = {'ensure': 2}   # falla en los dos nodos
    await svc.reconciliar_usuario(sessions, usuario_catedra.id, runner=runner)
    assert await svc.marcar_para_reintento(db, usuario_catedra.id) is True
    await db.commit()
    assert await svc.ciclo(sessions, runner=runner) == {usuario_catedra.id: 'lista'}
    assert await svc.marcar_para_reintento(db, 999999) is False
