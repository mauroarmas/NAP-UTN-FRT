"""Usuario no root en la consola de Linux IaaS (feature 021). Dobles del nodo y de Proxmox; no prueban un login real."""
import pytest
from sqlalchemy import select

from app.models.operacion_infraestructura import OperacionInfraestructura
from app.models.pedido import EstadoPedido
from app.models.servicio import Servicio
from app.utils.secretos import configured_keyring
from tests.capacity_helpers import perfil_capacidad  # noqa: F401
from tests.iaas_ssh_helpers import RunnerSsh, desplegar, nueva_clave, pedir_ubuntu
from tests.test_bases_iaas import configure


@pytest.fixture
async def entorno(monkeypatch, proxmox, perfil_capacidad):
    await configure(monkeypatch, proxmox)


async def _desplegado(client, db, engine, proxmox, auth_catedra, auth_admin, catedra, runner, clave=None):
    respuesta, plantilla = await pedir_ubuntu(client, db, auth_catedra, catedra, proxmox=proxmox, clave=clave or nueva_clave())
    assert respuesta.status_code == 201, respuesta.text
    pedido = await desplegar(client, db, engine, proxmox, runner, headers_admin=auth_admin,
        pedido_id=respuesta.json()['id'], plantilla=plantilla)
    return pedido, pedido.servicio_id


def _guest_password(servicio):
    return configured_keyring().decrypt(servicio.credenciales_encrypted, context=f'servicio:{servicio.id}:secretos')['guest_password']


# --- US1: servicio nuevo --------------------------------------------------------------------------

async def test_el_contenedor_se_crea_sin_contrasena_de_root(client, db, engine, proxmox, entorno,
        auth_catedra, auth_admin, catedra):
    await _desplegado(client, db, engine, proxmox, auth_catedra, auth_admin, catedra, RunnerSsh())
    assert proxmox.creados, 'no se creó ningún contenedor'
    assert all('password' not in creado for creado in proxmox.creados)


async def test_configure_recibe_la_contrasena_guardada_y_el_acceso_inicial_es_de_nap(client, db, engine, proxmox, entorno,
        auth_catedra, auth_admin, catedra):
    runner = RunnerSsh()
    pedido, sid = await _desplegado(client, db, engine, proxmox, auth_catedra, auth_admin, catedra, runner)
    assert pedido.estado == EstadoPedido.ACTIVO
    servicio = await db.get(Servicio, sid, populate_existing=True)
    configurar = [c for c in runner.calls if c['action'] == 'configure']
    assert len(configurar) == 1 and configurar[0]['password_consola'] == _guest_password(servicio)
    assert servicio.acceso_metadata['username'] == 'nap' and servicio.acceso_metadata['consola']['usuario'] == 'nap'
    detalle = await client.get(f'/servicios/{sid}/acceso', headers=auth_catedra)
    assert detalle.status_code == 200 and detalle.json()['consola_usuario'] == 'nap'
    revelado = await client.post(f'/servicios/{sid}/acceso/revelar', headers=auth_catedra, json={})
    assert revelado.status_code == 200, revelado.text
    assert revelado.json()['credenciales'] == {'usuario': 'nap', 'password': _guest_password(servicio)}
    assert 'root' not in revelado.text


async def test_un_nodo_que_no_confirma_la_contrasena_no_entrega_el_servicio(client, db, engine, proxmox, entorno,
        auth_catedra, auth_admin, catedra):
    runner = RunnerSsh(consola=None)   # nodo sin la versión nueva: ignora/omite el resultado de consola
    pedido, sid = await _desplegado(client, db, engine, proxmox, auth_catedra, auth_admin, catedra, runner)
    servicio = await db.get(Servicio, sid, populate_existing=True) if sid else None
    assert pedido.estado != EstadoPedido.ACTIVO
    assert servicio is None or servicio.disponibilidad_aplicacion != 'utilizable'
    assert servicio is None or servicio.acceso_metadata is None or servicio.acceso_metadata.get('username') != 'nap'


async def test_la_contrasena_no_queda_en_el_contexto_de_la_operacion_ni_en_la_asignacion(client, db, engine, proxmox, entorno,
        auth_catedra, auth_admin, catedra):
    pedido, sid = await _desplegado(client, db, engine, proxmox, auth_catedra, auth_admin, catedra, RunnerSsh())
    servicio = await db.get(Servicio, sid, populate_existing=True)
    clave = _guest_password(servicio)
    operaciones = (await db.scalars(select(OperacionInfraestructura).where(OperacionInfraestructura.servicio_id == sid))).all()
    assert all(clave not in str(op.contexto_seguro) for op in operaciones)
    assert clave not in str(servicio.asignacion_snapshot) and clave not in str(servicio.acceso_metadata)


# --- US2: servicios ya entregados ----------------------------------------------------------------

import hashlib

from app.models.servicio import EstadoServicio
from app.schemas.guest_runner import RunnerError
from tests.iaas_ssh_helpers import procesar


async def _como_entregado_antes_de_la_021(db, servicio, password_root='vieja-contrasena-de-root-0123456789abcd'):
    """Deja el servicio como lo dejaba la 017: acceso inicial = contraseña de root, sin marca de consola."""
    servicio.credenciales_encrypted = configured_keyring().encrypt({'guest_password': password_root},
        context=f'servicio:{servicio.id}:secretos')
    metadata = dict(servicio.acceso_metadata)
    metadata['username'] = 'root'
    metadata.pop('consola', None)
    servicio.acceso_metadata = metadata
    await db.commit()
    return password_root


async def _entregado_legacy(client, db, engine, proxmox, auth_catedra, auth_admin, catedra, runner):
    pedido, sid = await _desplegado(client, db, engine, proxmox, auth_catedra, auth_admin, catedra, runner)
    servicio = await db.get(Servicio, sid, populate_existing=True)
    vieja = await _como_entregado_antes_de_la_021(db, servicio)
    return sid, vieja


def _post(client, sid, headers, clave='actualizar-1'):
    return client.post(f'/servicios/{sid}/acceso-consola', headers=headers | {'Idempotency-Key': clave})


async def test_solo_administracion_puede_actualizar_el_acceso(client, db, engine, proxmox, entorno,
        auth_catedra, auth_admin, catedra):
    sid, _ = await _entregado_legacy(client, db, engine, proxmox, auth_catedra, auth_admin, catedra, RunnerSsh())
    assert (await _post(client, sid, auth_catedra)).status_code == 403


async def test_actualizar_pasa_el_servicio_a_nap_con_contrasena_nueva(client, db, engine, proxmox, entorno,
        auth_catedra, auth_admin, catedra):
    runner = RunnerSsh()
    sid, vieja = await _entregado_legacy(client, db, engine, proxmox, auth_catedra, auth_admin, catedra, runner)
    antes = len(runner.calls)
    respuesta = await _post(client, sid, auth_admin)
    assert respuesta.status_code == 202, respuesta.text
    assert vieja not in respuesta.text
    await procesar(engine, proxmox, runner)
    servicio = await db.get(Servicio, sid, populate_existing=True)
    nueva = _guest_password(servicio)
    assert nueva != vieja and len(nueva) >= 32
    assert servicio.acceso_metadata['username'] == 'nap' and servicio.acceso_metadata['consola']['usuario'] == 'nap'
    enviadas = [c['password_consola'] for c in runner.calls[antes:] if c['action'] == 'configure']
    assert enviadas == [nueva]
    revelado = await client.post(f'/servicios/{sid}/acceso/revelar', headers=auth_catedra, json={})
    assert revelado.json()['credenciales'] == {'usuario': 'nap', 'password': nueva}
    operacion = await db.scalar(select(OperacionInfraestructura).where(
        OperacionInfraestructura.servicio_id == sid, OperacionInfraestructura.motivo.like('%consola%')))
    assert operacion.estado == 'confirmada' and 'acceso_consola' not in (operacion.contexto_seguro or {})
    assert nueva not in str(operacion.contexto_seguro) and vieja not in str(operacion.contexto_seguro)


async def test_repetir_la_actualizacion_no_cambia_la_contrasena_ya_entregada(client, db, engine, proxmox, entorno,
        auth_catedra, auth_admin, catedra):
    runner = RunnerSsh()
    sid, _ = await _entregado_legacy(client, db, engine, proxmox, auth_catedra, auth_admin, catedra, runner)
    assert (await _post(client, sid, auth_admin)).status_code == 202
    await procesar(engine, proxmox, runner)
    servicio = await db.get(Servicio, sid, populate_existing=True)
    primera = _guest_password(servicio)
    for numero in range(3):
        respuesta = await _post(client, sid, auth_admin, clave=f'repetir-{numero}')
        assert respuesta.status_code == 200 and respuesta.json()['sin_cambios'] is True, respuesta.text
    await db.refresh(servicio)
    assert _guest_password(servicio) == primera


async def test_con_el_servicio_detenido_se_explica_y_no_cambia_nada(client, db, engine, proxmox, entorno,
        auth_catedra, auth_admin, catedra):
    sid, vieja = await _entregado_legacy(client, db, engine, proxmox, auth_catedra, auth_admin, catedra, RunnerSsh())
    servicio = await db.get(Servicio, sid, populate_existing=True)
    servicio.estado = EstadoServicio.STOPPED
    await db.commit()
    respuesta = await _post(client, sid, auth_admin)
    assert respuesta.status_code == 409 and respuesta.json()['detail']['codigo'] == 'servicio_detenido'
    await db.refresh(servicio)
    assert _guest_password(servicio) == vieja and servicio.acceso_metadata['username'] == 'root'


async def test_un_servicio_sin_clave_ssh_no_se_actualiza(client, db, engine, proxmox, entorno,
        auth_catedra, auth_admin, catedra):
    from app.models.clave_acceso_servicio import ClaveAccesoServicio
    sid, vieja = await _entregado_legacy(client, db, engine, proxmox, auth_catedra, auth_admin, catedra, RunnerSsh())
    fila = await db.scalar(select(ClaveAccesoServicio).where(ClaveAccesoServicio.servicio_id == sid))
    await db.delete(fila)
    await db.commit()
    respuesta = await _post(client, sid, auth_admin)
    assert respuesta.status_code == 409 and respuesta.json()['detail']['codigo'] == 'sin_clave'


async def test_un_fallo_definitivo_deja_la_credencial_y_el_usuario_anteriores(client, db, engine, proxmox, entorno,
        auth_catedra, auth_admin, catedra):
    sid, vieja = await _entregado_legacy(client, db, engine, proxmox, auth_catedra, auth_admin, catedra, RunnerSsh())
    assert (await _post(client, sid, auth_admin)).status_code == 202
    await procesar(engine, proxmox, RunnerSsh(error='SUDO_UNAVAILABLE'))
    servicio = await db.get(Servicio, sid, populate_existing=True)
    assert _guest_password(servicio) == vieja and servicio.acceso_metadata['username'] == 'root'


async def test_un_resultado_incierto_se_reintenta_con_la_misma_contrasena(client, db, engine, proxmox, entorno,
        auth_catedra, auth_admin, catedra):
    from datetime import timedelta
    from app.utils.clock import clock
    sid, vieja = await _entregado_legacy(client, db, engine, proxmox, auth_catedra, auth_admin, catedra, RunnerSsh())
    assert (await _post(client, sid, auth_admin)).status_code == 202
    runner = RunnerSsh(excepcion=RunnerError('UNCONFIRMED'))
    await procesar(engine, proxmox, runner, vueltas=4)
    servicio = await db.get(Servicio, sid, populate_existing=True)
    assert _guest_password(servicio) == vieja            # no se promovió nada sin confirmación
    primera = {c['password_consola'] for c in runner.calls if c['action'] == 'configure'}
    assert len(primera) == 1
    runner.excepcion = None
    operacion = await db.scalar(select(OperacionInfraestructura).where(
        OperacionInfraestructura.servicio_id == sid, OperacionInfraestructura.motivo.like('%consola%')))
    await db.refresh(operacion)
    assert operacion.estado in {'incierta', 'pendiente', 'en_curso'}
    operacion.next_poll_at = clock.now() - timedelta(seconds=1)
    await db.commit()
    await procesar(engine, proxmox, runner, vueltas=8)
    await db.refresh(servicio)
    todas = {c['password_consola'] for c in runner.calls if c['action'] == 'configure'}
    assert todas == primera and _guest_password(servicio) in primera       # el reintento usó la misma contraseña
    assert servicio.acceso_metadata['username'] == 'nap'


async def test_cambiar_la_clave_de_un_servicio_no_actualizado_no_toca_las_contrasenas(client, db, engine, proxmox, entorno,
        auth_catedra, auth_admin, catedra):
    runner = RunnerSsh()
    sid, vieja = await _entregado_legacy(client, db, engine, proxmox, auth_catedra, auth_admin, catedra, runner)
    antes = len(runner.calls)
    respuesta = await client.put(f'/servicios/{sid}/acceso-ssh', headers=auth_catedra | {'Idempotency-Key': 'nueva-clave'},
        json={'clave_publica': nueva_clave()})
    assert respuesta.status_code == 202, respuesta.text
    await procesar(engine, proxmox, runner)
    nuevos = [c for c in runner.calls[antes:] if c['action'] == 'configure']
    assert nuevos and all('password_consola' not in c for c in nuevos)
    servicio = await db.get(Servicio, sid, populate_existing=True)
    assert servicio.acceso_metadata['username'] == 'root' and _guest_password(servicio) == vieja
