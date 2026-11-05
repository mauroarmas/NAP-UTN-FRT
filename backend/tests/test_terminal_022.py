"""Relay de la terminal web (feature 022). Dobles del navegador y de la consola remota; no prueban Proxmox real."""
import asyncio
import json
import logging

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import get_settings
from app.models.evento_seguridad import EventoSeguridad
from app.models.identidad_consola import IdentidadConsola
from app.models.servicio import EstadoServicio
from app.models.sesion_terminal import SesionTerminal
from app.services import terminal_relay_service as relay
from app.utils.secretos import configured_keyring
from tests.capacity_helpers import materializado, perfil_capacidad  # noqa: F401
from tests.terminal_helpers import Navegador, Remoto, conector, esperar
from tests.test_convergencia_seguridad_009 import console_fixture

PASSWORD = 'Pw-' + 'aZ9_x' * 8


@pytest.fixture
def sessions(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
def configuracion(monkeypatch):
    monkeypatch.setattr(relay, 'VIGILANCIA_SEGUNDOS', 0.02)
    monkeypatch.setattr(get_settings(), 'terminal_max_sesiones', 3, raising=False)
    monkeypatch.setattr(get_settings(), 'terminal_inactividad_segundos', 900, raising=False)
    monkeypatch.setattr(get_settings(), 'terminal_max_mensaje_bytes', 65536, raising=False)


async def preparar(db, proxmox, catedra, usuario_catedra, template, admin, monkeypatch):
    servicio, _ = await materializado(db, proxmox, catedra, usuario_catedra, template)
    servicio.estado = EstadoServicio.RUNNING
    await db.commit()
    perfil = await console_fixture(db, usuario_catedra, servicio, admin, monkeypatch)
    perfil['nodos']['pve2'] = {'host': 'pve2.test', 'port': 8006}
    fila = await db.scalar(select(IdentidadConsola).where(IdentidadConsola.usuario_id == usuario_catedra.id))
    fila.password_cifrada = configured_keyring().encrypt({'password': PASSWORD}, context=f'identidad_consola:{usuario_catedra.id}')
    await db.commit()
    return servicio, fila.identidad


@pytest.fixture
def como(monkeypatch):
    """Autentica como una persona fija sin pasar por cookies (la autenticación real se prueba aparte)."""
    def _como(usuario_id):
        async def autenticado(sessions, websocket):
            return usuario_id
        monkeypatch.setattr(relay, 'autenticar_websocket', autenticado)
    return _como


async def correr(navegador, sessions, servicio_id, remoto=None, **kw):
    conectar = kw.pop('conectar', None) or conector(remoto or Remoto())
    tarea = asyncio.create_task(relay.servir(navegador, sessions, servicio_id, conectar=conectar, **kw))
    return tarea, conectar


async def test_la_terminal_abre_reenvia_en_ambos_sentidos_y_redimensiona(
        db, sessions, proxmox, perfil_capacidad, catedra, usuario_catedra, template, admin, monkeypatch, como):
    servicio, identidad = await preparar(db, proxmox, catedra, usuario_catedra, template, admin, monkeypatch)
    como(usuario_catedra.id)
    navegador, remoto = Navegador(), Remoto()
    tarea, conectar = await correr(navegador, sessions, servicio.id, remoto)
    assert await esperar(lambda: {'t': 'estado', 'e': 'abierta'} in navegador.mensajes())
    llamada = conectar.llamadas[0]
    assert (llamada['host'], llamada['puerto'], llamada['nodo'], llamada['identidad']) == ('pve1.test', 8006, 'pve1', identidad)
    assert llamada['password'] == PASSWORD and llamada['vmid'] == int(servicio.proxmox_vmid)
    navegador.teclear(b'ls -la\n')
    navegador.controlar(t='resize', cols=120, rows=30)
    remoto.emitir(b'total 0\r\n')
    assert await esperar(lambda: remoto.enviados == [b'ls -la\n'] and remoto.redimensionado == (120, 30))
    assert await esperar(lambda: navegador.salida_binaria() == b'total 0\r\n')
    navegador.irse()
    await asyncio.wait_for(tarea, 3)
    assert remoto.cerrado and navegador.cierre()['motivo'] == 'persona'


@pytest.mark.parametrize('caso, codigo', [('detenido', 4409), ('sin_vigencia', 4409), ('identidad_no_lista', 4409),
                                          ('catedra_ajena', 4403), ('sin_compuerta', 4409)])
async def test_la_admision_rechaza_antes_de_tocar_la_infraestructura(
        db, sessions, proxmox, perfil_capacidad, catedra, usuario_catedra, template, admin, monkeypatch, como, caso, codigo):
    servicio, _ = await preparar(db, proxmox, catedra, usuario_catedra, template, admin, monkeypatch)
    persona = usuario_catedra
    if caso == 'detenido':
        servicio.estado = EstadoServicio.STOPPED
    elif caso == 'sin_vigencia':
        from app.models.vigencia import VigenciaAutorizada
        for v in (await db.scalars(select(VigenciaAutorizada).where(VigenciaAutorizada.servicio_id == servicio.id))).all():
            await db.delete(v)
    elif caso == 'identidad_no_lista':
        (await db.scalar(select(IdentidadConsola))).estado = 'con_error'
    elif caso == 'sin_compuerta':
        monkeypatch.setattr(get_settings(), 'console_access_profile', {})
    elif caso == 'catedra_ajena':
        from tests import factories
        from app.models.usuario import RolUsuario
        persona = await factories.crear_usuario(db, username='ajena', rol=RolUsuario.CATEDRA_ADMIN)
        await factories.crear_catedra(db, nombre='Otra', titular_id=persona.id)
    await db.commit()
    como(persona.id)
    navegador = Navegador()
    tarea, conectar = await correr(navegador, sessions, servicio.id)
    await asyncio.wait_for(tarea, 3)
    assert navegador.aceptado and navegador.codigo == codigo and navegador.cierre()['mensaje']
    assert conectar.llamadas == []
    assert (await db.scalars(select(SesionTerminal))).all() == []
    for _, valor in navegador.salidas:
        assert 'pve1.test' not in str(valor) and PASSWORD not in str(valor) and 'nap-u' not in str(valor)


async def test_sin_sesion_del_portal_no_se_acepta_nada(db, sessions, proxmox, perfil_capacidad, catedra, usuario_catedra,
                                                      template, admin, monkeypatch):
    servicio, _ = await preparar(db, proxmox, catedra, usuario_catedra, template, admin, monkeypatch)
    navegador = Navegador(cookies={})           # sin cookie
    tarea, conectar = await correr(navegador, sessions, servicio.id)
    await asyncio.wait_for(tarea, 3)
    assert navegador.codigo == 4401 and conectar.llamadas == []


async def test_con_una_sesion_real_del_portal_se_autentica(db, sessions, proxmox, perfil_capacidad, catedra, usuario_catedra,
                                                          template, admin, monkeypatch):
    from tests.auth_helpers import headers_para
    servicio, _ = await preparar(db, proxmox, catedra, usuario_catedra, template, admin, monkeypatch)
    cabeceras = await headers_para(db, usuario_catedra)
    nombre, valor = cabeceras['Cookie'].split('=', 1)
    navegador, remoto = Navegador(cookies={nombre: valor}, headers={'origin': cabeceras['Origin']}), Remoto()
    tarea, conectar = await correr(navegador, sessions, servicio.id, remoto)
    assert await esperar(lambda: {'t': 'estado', 'e': 'abierta'} in navegador.mensajes())
    navegador.irse()
    await asyncio.wait_for(tarea, 3)


async def test_el_cupo_por_persona_rechaza_la_terminal_que_lo_supera(
        db, sessions, proxmox, perfil_capacidad, catedra, usuario_catedra, template, admin, monkeypatch, como):
    servicio, _ = await preparar(db, proxmox, catedra, usuario_catedra, template, admin, monkeypatch)
    monkeypatch.setattr(get_settings(), 'terminal_max_sesiones', 2, raising=False)
    como(usuario_catedra.id)
    abiertas = []
    for _ in range(2):
        nav, rem = Navegador(), Remoto()
        tarea, _c = await correr(nav, sessions, servicio.id, rem)
        assert await esperar(lambda: {'t': 'estado', 'e': 'abierta'} in nav.mensajes())
        abiertas.append((nav, tarea))
    tercera, tarea3 = Navegador(), None
    tarea3, conectar = await correr(tercera, sessions, servicio.id)
    await asyncio.wait_for(tarea3, 3)
    assert tercera.codigo == 4429 and 'máximo' in tercera.cierre()['mensaje'] and conectar.llamadas == []
    for nav, tarea in abiertas:
        nav.irse()
        await asyncio.wait_for(tarea, 3)
    cuarta, rem = Navegador(), Remoto()
    t4, _c = await correr(cuarta, sessions, servicio.id, rem)           # al cerrar, el cupo se libera
    assert await esperar(lambda: {'t': 'estado', 'e': 'abierta'} in cuarta.mensajes())
    cuarta.irse()
    await asyncio.wait_for(t4, 3)


async def test_failover_al_otro_nodo_y_reintento_unico_de_la_primera_apertura(
        db, sessions, proxmox, perfil_capacidad, catedra, usuario_catedra, template, admin, monkeypatch, como):
    servicio, _ = await preparar(db, proxmox, catedra, usuario_catedra, template, admin, monkeypatch)
    como(usuario_catedra.id)
    # a) un corte transitorio en el primer intento: se reintenta una vez sobre el mismo nodo, sin avisar a la persona
    nav, rem = Navegador(), Remoto()
    tarea, conectar = await correr(nav, sessions, servicio.id, conectar=conector(rem, fallos=1))
    assert await esperar(lambda: {'t': 'estado', 'e': 'abierta'} in nav.mensajes())
    assert [c['host'] for c in conectar.llamadas] == ['pve1.test', 'pve1.test']
    assert not any(m.get('t') == 'aviso' for m in nav.mensajes())
    nav.irse(); await asyncio.wait_for(tarea, 3)
    # b) el nodo del contenedor no responde: se prueba el otro
    nav, rem = Navegador(), Remoto()
    tarea, conectar = await correr(nav, sessions, servicio.id, conectar=conector(rem, falla_hosts={'pve1.test'}))
    assert await esperar(lambda: {'t': 'estado', 'e': 'abierta'} in nav.mensajes())
    assert [c['host'] for c in conectar.llamadas] == ['pve1.test', 'pve1.test', 'pve2.test']
    assert all(c['nodo'] == 'pve1' for c in conectar.llamadas)          # el contenedor es siempre el mismo
    nav.irse(); await asyncio.wait_for(tarea, 3)
    # c) ningún nodo responde: mensaje claro, sin destino equivocado ni sesión colgada
    nav = Navegador()
    tarea, conectar = await correr(nav, sessions, servicio.id, conectar=conector(Remoto(), falla_hosts={'pve1.test', 'pve2.test'}))
    await asyncio.wait_for(tarea, 3)
    assert nav.codigo == 4503 and 'no está disponible' in nav.cierre()['mensaje']
    assert [s.motivo_cierre for s in (await db.scalars(select(SesionTerminal))).all()][-1] == 'error'


async def test_un_mensaje_demasiado_grande_corta_la_sesion(
        db, sessions, proxmox, perfil_capacidad, catedra, usuario_catedra, template, admin, monkeypatch, como):
    servicio, _ = await preparar(db, proxmox, catedra, usuario_catedra, template, admin, monkeypatch)
    monkeypatch.setattr(get_settings(), 'terminal_max_mensaje_bytes', 1024, raising=False)
    como(usuario_catedra.id)
    nav, rem = Navegador(), Remoto()
    tarea, _c = await correr(nav, sessions, servicio.id, rem)
    assert await esperar(lambda: {'t': 'estado', 'e': 'abierta'} in nav.mensajes())
    nav.teclear(b'x' * 2000)
    await asyncio.wait_for(tarea, 3)
    assert rem.enviados == [] and nav.cierre()['motivo'] == 'error'


async def test_se_cierra_por_inactividad_y_avisa_antes(
        db, sessions, proxmox, perfil_capacidad, catedra, usuario_catedra, template, admin, monkeypatch, como):
    servicio, _ = await preparar(db, proxmox, catedra, usuario_catedra, template, admin, monkeypatch)
    monkeypatch.setattr(get_settings(), 'terminal_inactividad_segundos', 120, raising=False)
    como(usuario_catedra.id)
    reloj_falso = {'t': 0.0}
    def reloj():
        reloj_falso['t'] += 5.0                    # cada consulta del vigilante "pasan" 5 segundos
        return reloj_falso['t']
    nav, rem = Navegador(), Remoto()
    tarea, _c = await correr(nav, sessions, servicio.id, rem, reloj=reloj)
    await asyncio.wait_for(tarea, 5)
    avisos = [m for m in nav.mensajes() if m.get('t') == 'aviso']
    assert avisos and 'cerrará en 1 minuto' in avisos[0]['mensaje']
    assert nav.cierre()['motivo'] == 'inactividad' and nav.codigo == 4408
    assert (await db.scalar(select(SesionTerminal))).motivo_cierre == 'inactividad'


async def test_la_actividad_de_la_persona_mantiene_viva_la_terminal_pero_la_salida_no(
        db, sessions, proxmox, perfil_capacidad, catedra, usuario_catedra, template, admin, monkeypatch, como):
    servicio, _ = await preparar(db, proxmox, catedra, usuario_catedra, template, admin, monkeypatch)
    monkeypatch.setattr(get_settings(), 'terminal_inactividad_segundos', 120, raising=False)
    como(usuario_catedra.id)
    t = {'v': 0.0}
    def reloj():
        t['v'] += 5.0
        return t['v']
    nav, rem = Navegador(), Remoto()
    tarea, _c = await correr(nav, sessions, servicio.id, rem, reloj=reloj)
    assert await esperar(lambda: {'t': 'estado', 'e': 'abierta'} in nav.mensajes())
    for _ in range(15):                                 # la persona escribe seguido: no se cierra por inactividad
        nav.teclear(b'a')
        await asyncio.sleep(0.03)
        rem.emitir(b'x')                                # la salida del contenedor NO cuenta como actividad
    assert not tarea.done()
    nav.irse()
    await asyncio.wait_for(tarea, 5)


@pytest.mark.parametrize('pedido, motivo, codigo', [('retiro', 'retiro', 4410), ('baja', 'baja', 4410), ('detencion', 'detencion', 4410),
                                                    ('cuenta', 'cuenta', 4410), ('administracion', 'administracion', 4410)])
async def test_el_cierre_solicitado_corta_de_inmediato_con_su_motivo(
        db, sessions, proxmox, perfil_capacidad, catedra, usuario_catedra, template, admin, monkeypatch, como, pedido, motivo, codigo):
    from app.services import terminal_sesiones_service as ts
    servicio, _ = await preparar(db, proxmox, catedra, usuario_catedra, template, admin, monkeypatch)
    como(usuario_catedra.id)
    nav, rem = Navegador(), Remoto()
    tarea, _c = await correr(nav, sessions, servicio.id, rem)
    assert await esperar(lambda: {'t': 'estado', 'e': 'abierta'} in nav.mensajes())
    async with sessions() as s, s.begin():
        assert await ts.solicitar_cierre(s, motivo=pedido, servicio_id=servicio.id) == 1
    await asyncio.wait_for(tarea, 3)
    assert nav.cierre()['motivo'] == motivo and nav.codigo == codigo and rem.cerrado


async def test_si_la_consola_remota_se_corta_la_persona_lo_ve(
        db, sessions, proxmox, perfil_capacidad, catedra, usuario_catedra, template, admin, monkeypatch, como):
    servicio, _ = await preparar(db, proxmox, catedra, usuario_catedra, template, admin, monkeypatch)
    como(usuario_catedra.id)
    nav, rem = Navegador(), Remoto()
    tarea, _c = await correr(nav, sessions, servicio.id, rem)
    assert await esperar(lambda: {'t': 'estado', 'e': 'abierta'} in nav.mensajes())
    rem.cortar()
    await asyncio.wait_for(tarea, 3)
    assert nav.cierre()['motivo'] == 'error'


async def test_si_la_sesion_del_portal_deja_de_valer_la_terminal_se_cierra(
        db, sessions, proxmox, perfil_capacidad, catedra, usuario_catedra, template, admin, monkeypatch):
    servicio, _ = await preparar(db, proxmox, catedra, usuario_catedra, template, admin, monkeypatch)
    llamadas = {'n': 0}
    async def autenticado(sessions_, websocket):
        llamadas['n'] += 1
        if llamadas['n'] > 1:
            raise RuntimeError('sesión revocada')       # la primera vez (apertura) es válida; luego se revoca
        return usuario_catedra.id
    monkeypatch.setattr(relay, 'autenticar_websocket', autenticado)
    monkeypatch.setattr(relay, 'REVALIDAR_SEGUNDOS', 0.0)
    nav, rem = Navegador(), Remoto()
    tarea, _c = await correr(nav, sessions, servicio.id, rem)
    await asyncio.wait_for(tarea, 3)
    assert nav.cierre()['motivo'] == 'cuenta' and nav.codigo == 4410


async def test_auditoria_sin_contenido_ni_contrasenas(
        db, sessions, proxmox, perfil_capacidad, catedra, usuario_catedra, template, admin, monkeypatch, como, caplog):
    caplog.set_level(logging.DEBUG)
    servicio, identidad = await preparar(db, proxmox, catedra, usuario_catedra, template, admin, monkeypatch)
    como(usuario_catedra.id)
    nav, rem = Navegador(), Remoto()
    tarea, _c = await correr(nav, sessions, servicio.id, rem)
    assert await esperar(lambda: {'t': 'estado', 'e': 'abierta'} in nav.mensajes())
    nav.teclear(b'echo TEXTO-SECRETO-TECLEADO\n')
    rem.emitir(b'TEXTO-SECRETO-MOSTRADO\r\n')
    assert await esperar(lambda: rem.enviados)
    nav.irse()
    await asyncio.wait_for(tarea, 3)
    eventos = (await db.scalars(select(EventoSeguridad).where(EventoSeguridad.accion.like('terminal_%')))).all()
    assert [e.accion for e in sorted(eventos, key=lambda e: e.creado_at)] == ['terminal_abierta', 'terminal_cerrada']
    cierre = next(e for e in eventos if e.accion == 'terminal_cerrada')
    assert cierre.referencia == f'servicio:{servicio.id}' and 'persona' in cierre.motivo and 'duracion=' in cierre.motivo
    base = '\n'.join(map(repr, (await db.execute(text('select * from sesiones_terminal'))).fetchall())) + \
           '\n'.join(map(repr, (await db.execute(text('select * from eventos_seguridad'))).fetchall()))
    for secreto in ('TEXTO-SECRETO-TECLEADO', 'TEXTO-SECRETO-MOSTRADO', PASSWORD):
        assert secreto not in base and secreto not in caplog.text
    assert PASSWORD not in repr(nav.salidas)


def test_un_origen_no_permitido_se_rechaza_antes_de_aceptar_el_websocket():
    from starlette.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect
    from app.main import app
    cliente = TestClient(app)
    for cabeceras in ({'Origin': 'https://sitio-ajeno.example'}, {}):
        with pytest.raises(WebSocketDisconnect) as exc:
            with cliente.websocket_connect('/api/v1/servicios/1/terminal', headers=cabeceras):
                pass
        assert exc.value.code == 1008


async def test_el_portal_usa_portal_host_y_el_navegador_nunca_recibe_ninguna_direccion(
        db, sessions, proxmox, perfil_capacidad, catedra, usuario_catedra, template, admin, monkeypatch, como):
    servicio, _ = await preparar(db, proxmox, catedra, usuario_catedra, template, admin, monkeypatch)
    get_settings().console_access_profile['nodos']['pve1']['portal_host'] = 'pve1.interno.test'
    como(usuario_catedra.id)
    nav, rem = Navegador(), Remoto()
    tarea, conectar = await correr(nav, sessions, servicio.id, rem)
    assert await esperar(lambda: {'t': 'estado', 'e': 'abierta'} in nav.mensajes())
    assert conectar.llamadas[0]['host'] == 'pve1.interno.test'
    assert 'pve1' not in repr(nav.salidas)
    nav.irse(); await asyncio.wait_for(tarea, 3)
