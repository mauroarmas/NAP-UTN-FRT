"""Acceso SSH a Linux IaaS: pedido, despliegue, detalle de acceso y reemplazo de clave (feature 017)."""
import pytest
from sqlalchemy import select

from app.models.clave_acceso_servicio import ClaveAccesoServicio
from app.models.operacion_infraestructura import OperacionInfraestructura
from app.models.pedido import EstadoPedido, Pedido
from app.models.servicio import EstadoServicio, Servicio
from app.models.usuario import RolUsuario
from tests import factories
from tests.auth_helpers import headers_para
from tests.capacity_helpers import perfil_capacidad  # noqa: F401
from tests.iaas_ssh_helpers import RunnerSsh, desplegar, nueva_clave, pedir_ubuntu, procesar
from tests.test_bases_iaas import configure


@pytest.fixture
async def entorno(monkeypatch, proxmox, perfil_capacidad):
    await configure(monkeypatch, proxmox)


async def _desplegado(client, db, engine, proxmox, auth_catedra, auth_admin, catedra, runner, clave):
    respuesta, plantilla = await pedir_ubuntu(client, db, auth_catedra, catedra, proxmox=proxmox, clave=clave)
    assert respuesta.status_code == 201, respuesta.text
    pedido = await desplegar(client, db, engine, proxmox, runner, headers_admin=auth_admin,
        pedido_id=respuesta.json()['id'], plantilla=plantilla)
    return pedido, pedido.servicio_id


# --- Pedido -----------------------------------------------------------------------------------

async def test_pedido_linux_sin_clave_se_rechaza(client, db, proxmox, entorno, auth_catedra, catedra):
    respuesta, _ = await pedir_ubuntu(client, db, auth_catedra, catedra, proxmox=proxmox, clave=None)
    assert respuesta.status_code == 422 and respuesta.json()['detail']['codigo'] == 'clave_ssh_requerida'


@pytest.mark.parametrize('clave,codigo', [
    ('-----BEGIN OPENSSH PRIVATE KEY-----\nabc\n-----END OPENSSH PRIVATE KEY-----', 'clave_ssh_privada'),
    ('esto no es una clave', 'clave_ssh_invalida'),
    ('ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAAAgQ', 'clave_ssh_invalida'),
])
async def test_pedido_linux_con_clave_invalida_se_explica(client, db, proxmox, entorno, auth_catedra, catedra, clave, codigo):
    respuesta, _ = await pedir_ubuntu(client, db, auth_catedra, catedra, proxmox=proxmox, clave=clave)
    assert respuesta.status_code == 422 and respuesta.json()['detail']['codigo'] == codigo
    assert 'BEGIN OPENSSH' not in respuesta.text or codigo == 'clave_ssh_privada'


async def test_pedido_guarda_la_clave_normalizada_sin_comentario(client, db, proxmox, entorno, auth_catedra, catedra):
    clave = nueva_clave('docente@equipo con comentario')
    respuesta, _ = await pedir_ubuntu(client, db, auth_catedra, catedra, proxmox=proxmox, clave=clave)
    assert respuesta.status_code == 201, respuesta.text
    pedido = await db.get(Pedido, respuesta.json()['id'])
    assert pedido.parametros_extra['clave_ssh_publica'] == ' '.join(clave.split()[:2])


async def test_clave_en_un_servicio_que_no_la_usa_se_rechaza(client, db, proxmox, entorno, auth_catedra, catedra, template):
    cuerpo = {'template_id': template.id, 'modelo_servicio': 'iaas', 'catedra_id': catedra.id,
        'descripcion_requerimientos': 'Prueba', 'parametros_extra': {'clave_ssh_publica': nueva_clave()},
        'vigencia': {'tipo': 'personalizado', 'desde': '2099-03-01', 'hasta': '2099-03-10'}}
    respuesta = await client.post('/pedidos/', headers=auth_catedra | {'Idempotency-Key': 'sin-uso'}, json=cuerpo)
    assert respuesta.status_code == 422 and respuesta.json()['detail']['codigo'] in {'clave_ssh_no_aplica', 'vigencia_finalizada', 'plantilla_incompatible'}


# --- Despliegue y detalle ------------------------------------------------------------------------

async def test_despliegue_aplica_la_clave_y_el_detalle_muestra_como_conectarse(client, db, engine, proxmox, entorno,
        auth_catedra, auth_admin, catedra):
    runner, clave = RunnerSsh(), nueva_clave()
    pedido, sid = await _desplegado(client, db, engine, proxmox, auth_catedra, auth_admin, catedra, runner, clave)
    servicio = await db.get(Servicio, sid, populate_existing=True) if sid else None
    assert pedido.estado == EstadoPedido.ACTIVO and servicio.disponibilidad_aplicacion == 'utilizable'
    configurar = [c for c in runner.calls if c['action'] == 'configure']
    assert len(configurar) == 1 and configurar[0]['clave_publica'] == ' '.join(clave.split()[:2]) and configurar[0]['revision'] == 1
    fila = await db.scalar(select(ClaveAccesoServicio).where(ClaveAccesoServicio.servicio_id == sid))
    assert fila.revision == fila.aplicada_revision == 1 and fila.usuario == 'nap'
    detalle = await client.get(f'/servicios/{sid}/acceso', headers=auth_catedra)
    assert detalle.status_code == 200, detalle.text
    ssh = detalle.json()['acceso_ssh']
    assert ssh['estado'] == 'aplicada' and ssh['puede_conectar'] is True and ssh['usuario'] == 'nap'
    assert ssh['comando'] == f"ssh nap@{ssh['direccion']}" and ssh['huella'].startswith('SHA256:')
    assert detalle.json()['metodo'] == 'consola'  # la consola queda como estaba (FR-015)
    assert clave.split()[1] not in detalle.text  # solo la huella, nunca la clave


async def test_un_rechazo_definitivo_del_nodo_no_entrega_el_servicio(client, db, engine, proxmox, entorno,
        auth_catedra, auth_admin, catedra):
    runner = RunnerSsh(error='SSHD_UNAVAILABLE')
    pedido, sid = await _desplegado(client, db, engine, proxmox, auth_catedra, auth_admin, catedra, runner, nueva_clave())
    servicio = await db.get(Servicio, sid, populate_existing=True) if sid else None
    assert pedido.estado == EstadoPedido.ERROR
    operacion = await db.scalar(select(OperacionInfraestructura).where(OperacionInfraestructura.pedido_id == pedido.id))
    assert operacion.estado == 'fallida' and operacion.error_codigo == 'acceso_ssh_sshd_unavailable'
    assert servicio is None or servicio.disponibilidad_aplicacion != 'utilizable'


async def test_un_resultado_incierto_se_reintenta_con_la_misma_revision(client, db, engine, proxmox, entorno,
        auth_catedra, auth_admin, catedra):
    from app.schemas.guest_runner import RunnerError
    runner = RunnerSsh(excepcion=RunnerError('UNCONFIRMED'))
    pedido, sid = await _desplegado(client, db, engine, proxmox, auth_catedra, auth_admin, catedra, runner, nueva_clave())
    servicio = await db.get(Servicio, sid, populate_existing=True) if sid else None
    assert pedido.estado != EstadoPedido.ACTIVO
    operacion = await db.scalar(select(OperacionInfraestructura).where(OperacionInfraestructura.pedido_id == pedido.id))
    assert operacion.estado in {'incierta', 'pendiente', 'en_curso'}
    runner.excepcion = None
    from datetime import timedelta
    from app.utils.clock import clock
    await db.refresh(operacion)
    operacion.next_poll_at = clock.now() - timedelta(seconds=1)
    await db.commit()
    await procesar(engine, proxmox, runner, vueltas=8)
    await db.refresh(pedido)
    assert pedido.estado == EstadoPedido.ACTIVO
    revisiones = {c['revision'] for c in runner.calls if c['action'] == 'configure'}
    assert revisiones == {1}


async def test_con_el_servicio_detenido_no_se_ofrece_el_comando(client, db, engine, proxmox, entorno,
        auth_catedra, auth_admin, catedra):
    pedido, sid = await _desplegado(client, db, engine, proxmox, auth_catedra, auth_admin, catedra, RunnerSsh(), nueva_clave())
    servicio = await db.get(Servicio, sid, populate_existing=True) if sid else None
    servicio.estado = EstadoServicio.STOPPED
    await db.commit()
    ssh = (await client.get(f'/servicios/{sid}/acceso', headers=auth_catedra)).json()['acceso_ssh']
    assert ssh['estado'] == 'aplicada' and ssh['puede_conectar'] is False and ssh['comando'] is None
    assert 'Iniciá el servicio' in ssh['motivo']


# --- Reemplazo y alta tardía -----------------------------------------------------------------------

async def test_reemplazar_la_clave_reaplica_con_revision_nueva(client, db, engine, proxmox, entorno,
        auth_catedra, auth_admin, catedra):
    runner = RunnerSsh()
    _, sid = await _desplegado(client, db, engine, proxmox, auth_catedra, auth_admin, catedra, runner, nueva_clave())
    servicio = await db.get(Servicio, sid, populate_existing=True) if sid else None
    nueva = nueva_clave()
    respuesta = await client.put(f'/servicios/{sid}/acceso-ssh', headers=auth_catedra | {'Idempotency-Key': 'rem-1'},
        json={'clave_publica': nueva})
    assert respuesta.status_code == 202, respuesta.text
    assert respuesta.json()['revision'] == 2 and respuesta.json()['estado'] == 'pendiente'
    duplicado = await client.put(f'/servicios/{sid}/acceso-ssh', headers=auth_catedra | {'Idempotency-Key': 'otra'},
        json={'clave_publica': nueva_clave()})
    assert duplicado.status_code == 409 and duplicado.json()['detail']['codigo'] == 'operacion_en_curso'
    await procesar(engine, proxmox, runner)
    fila = await db.scalar(select(ClaveAccesoServicio).where(ClaveAccesoServicio.servicio_id == sid))
    await db.refresh(fila)
    assert fila.revision == fila.aplicada_revision == 2
    ultima = [c for c in runner.calls if c['action'] == 'configure'][-1]
    assert ultima['revision'] == 2 and ultima['clave_publica'] == ' '.join(nueva.split()[:2])
    ssh = (await client.get(f'/servicios/{sid}/acceso', headers=auth_catedra)).json()['acceso_ssh']
    assert ssh['estado'] == 'aplicada' and ssh['puede_conectar'] is True and ssh['direccion']  # la dirección se conserva


async def test_repetir_la_misma_clave_ya_aplicada_no_hace_nada(client, db, engine, proxmox, entorno,
        auth_catedra, auth_admin, catedra):
    runner, clave = RunnerSsh(), nueva_clave()
    _, sid = await _desplegado(client, db, engine, proxmox, auth_catedra, auth_admin, catedra, runner, clave)
    servicio = await db.get(Servicio, sid, populate_existing=True) if sid else None
    antes = len(runner.calls)
    respuesta = await client.put(f'/servicios/{sid}/acceso-ssh', headers=auth_catedra | {'Idempotency-Key': 'igual'},
        json={'clave_publica': clave})
    assert respuesta.status_code == 200 and respuesta.json()['sin_cambios'] is True
    assert len(runner.calls) == antes


async def test_una_persona_ajena_no_puede_cambiar_la_clave(client, db, engine, proxmox, entorno,
        auth_catedra, auth_admin, catedra):
    _, sid = await _desplegado(client, db, engine, proxmox, auth_catedra, auth_admin, catedra, RunnerSsh(), nueva_clave())
    servicio = await db.get(Servicio, sid, populate_existing=True) if sid else None
    ajeno = await factories.crear_usuario(db, 'ajeno', rol=RolUsuario.CATEDRA_ADMIN)
    await factories.crear_catedra(db, nombre='Ajena', titular_id=ajeno.id)
    respuesta = await client.put(f'/servicios/{sid}/acceso-ssh',
        headers=(await headers_para(db, ajeno)) | {'Idempotency-Key': 'intruso'}, json={'clave_publica': nueva_clave()})
    assert respuesta.status_code in {403, 404}
    assert (await db.scalar(select(ClaveAccesoServicio).where(ClaveAccesoServicio.servicio_id == sid))).revision == 1


async def test_clave_invalida_en_el_reemplazo_se_explica(client, db, engine, proxmox, entorno, auth_catedra, auth_admin, catedra):
    _, sid = await _desplegado(client, db, engine, proxmox, auth_catedra, auth_admin, catedra, RunnerSsh(), nueva_clave())
    servicio = await db.get(Servicio, sid, populate_existing=True) if sid else None
    respuesta = await client.put(f'/servicios/{sid}/acceso-ssh', headers=auth_catedra | {'Idempotency-Key': 'mala'},
        json={'clave_publica': '-----BEGIN OPENSSH PRIVATE KEY-----'})
    assert respuesta.status_code == 422 and respuesta.json()['detail']['codigo'] == 'clave_ssh_privada'


async def test_servicio_detenido_no_admite_cambio_de_clave(client, db, engine, proxmox, entorno, auth_catedra, auth_admin, catedra):
    _, sid = await _desplegado(client, db, engine, proxmox, auth_catedra, auth_admin, catedra, RunnerSsh(), nueva_clave())
    servicio = await db.get(Servicio, sid, populate_existing=True) if sid else None
    servicio.estado = EstadoServicio.STOPPED
    await db.commit()
    respuesta = await client.put(f'/servicios/{sid}/acceso-ssh', headers=auth_catedra | {'Idempotency-Key': 'parado'},
        json={'clave_publica': nueva_clave()})
    assert respuesta.status_code == 409 and respuesta.json()['detail']['codigo'] == 'servicio_detenido'


async def test_alta_tardia_en_un_servicio_sin_clave(client, db, engine, proxmox, entorno, auth_catedra, auth_admin, catedra):
    """Un Linux entregado antes de esta función (sin fila) puede incorporar su clave."""
    runner = RunnerSsh()
    _, sid = await _desplegado(client, db, engine, proxmox, auth_catedra, auth_admin, catedra, runner, nueva_clave())
    servicio = await db.get(Servicio, sid, populate_existing=True) if sid else None
    fila = await db.scalar(select(ClaveAccesoServicio).where(ClaveAccesoServicio.servicio_id == sid))
    await db.delete(fila)
    await db.commit()
    antes = (await client.get(f'/servicios/{sid}/acceso', headers=auth_catedra)).json()['acceso_ssh']
    assert antes['estado'] == 'sin_clave' and antes['comando'] is None and antes['puede_conectar'] is False
    respuesta = await client.put(f'/servicios/{sid}/acceso-ssh', headers=auth_catedra | {'Idempotency-Key': 'tardia'},
        json={'clave_publica': nueva_clave()})
    assert respuesta.status_code == 202 and respuesta.json()['revision'] == 1
    await procesar(engine, proxmox, runner)
    despues = (await client.get(f'/servicios/{sid}/acceso', headers=auth_catedra)).json()['acceso_ssh']
    assert despues['estado'] == 'aplicada' and despues['puede_conectar'] is True


# --- Ciclo de vida -----------------------------------------------------------------------------------

async def test_detener_e_iniciar_conserva_la_clave_aplicada(client, db, engine, proxmox, entorno, auth_catedra, auth_admin, catedra):
    runner = RunnerSsh()
    _, sid = await _desplegado(client, db, engine, proxmox, auth_catedra, auth_admin, catedra, runner, nueva_clave())
    servicio = await db.get(Servicio, sid, populate_existing=True)
    servicio.estado = EstadoServicio.STOPPED
    await db.commit()
    parado = (await client.get(f'/servicios/{sid}/acceso', headers=auth_catedra)).json()['acceso_ssh']
    assert parado['puede_conectar'] is False and parado['estado'] == 'aplicada'
    servicio = await db.get(Servicio, sid, populate_existing=True)
    servicio.estado = EstadoServicio.RUNNING
    await db.commit()
    iniciado = (await client.get(f'/servicios/{sid}/acceso', headers=auth_catedra)).json()['acceso_ssh']
    assert iniciado['puede_conectar'] is True and iniciado['comando'] == f"ssh nap@{iniciado['direccion']}"
    assert len([c for c in runner.calls if c['action'] == 'configure']) == 1  # iniciar no reenvía la configuración


async def test_un_servicio_dado_de_baja_deja_de_mostrar_el_acceso(client, db, engine, proxmox, entorno, auth_catedra, auth_admin, catedra):
    from datetime import datetime
    _, sid = await _desplegado(client, db, engine, proxmox, auth_catedra, auth_admin, catedra, RunnerSsh(), nueva_clave())
    servicio = await db.get(Servicio, sid, populate_existing=True)
    servicio.deleted_at = datetime(2026, 11, 3)
    await db.commit()
    assert (await client.get(f'/servicios/{sid}/acceso', headers=auth_catedra)).status_code == 404
    reemplazo = await client.put(f'/servicios/{sid}/acceso-ssh', headers=auth_catedra | {'Idempotency-Key': 'baja'},
        json={'clave_publica': nueva_clave()})
    assert reemplazo.status_code == 404


async def test_cada_servicio_tiene_su_propia_clave(client, db, engine, proxmox, entorno, auth_catedra, auth_admin, catedra):
    runner = RunnerSsh()
    primera, segunda = nueva_clave(), nueva_clave()
    _, uno = await _desplegado(client, db, engine, proxmox, auth_catedra, auth_admin, catedra, runner, primera)
    respuesta, plantilla = await pedir_ubuntu(client, db, auth_catedra, catedra, proxmox=proxmox, clave=segunda, clave_http='pedido-dos')
    assert respuesta.status_code == 201, respuesta.text
    pedido = await desplegar(client, db, engine, proxmox, runner, headers_admin=auth_admin,
        pedido_id=respuesta.json()['id'], plantilla=plantilla)
    dos = pedido.servicio_id
    filas = {f.servicio_id: f for f in (await db.scalars(select(ClaveAccesoServicio))).all()}
    assert uno != dos and filas[uno].huella_sha256 != filas[dos].huella_sha256
    enviadas = {c['clave_publica'] for c in runner.calls if c['action'] == 'configure'}
    assert enviadas == {' '.join(primera.split()[:2]), ' '.join(segunda.split()[:2])}


# --- IP observada ------------------------------------------------------------------------------------

async def test_el_comando_usa_la_ip_que_el_contenedor_tiene_de_verdad(client, db, engine, proxmox, entorno,
        auth_catedra, auth_admin, catedra):
    """El DHCP puede no respetar la reserva: el comando tiene que apuntar a la IP observada."""
    _, sid = await _desplegado(client, db, engine, proxmox, auth_catedra, auth_admin, catedra,
        RunnerSsh(direccion='10.20.0.99'), nueva_clave())
    detalle = (await client.get(f'/servicios/{sid}/acceso', headers=auth_catedra)).json()['acceso_ssh']
    assert detalle['direccion'] == '10.20.0.99' and detalle['comando'] == 'ssh nap@10.20.0.99'
    servicio = await db.get(Servicio, sid, populate_existing=True)
    assert servicio.acceso_metadata['addresses'] != ['10.20.0.99']  # la reservada se conserva aparte


async def test_sin_ip_observada_se_usa_la_reservada(client, db, engine, proxmox, entorno, auth_catedra, auth_admin, catedra):
    _, sid = await _desplegado(client, db, engine, proxmox, auth_catedra, auth_admin, catedra, RunnerSsh(), nueva_clave())
    servicio = await db.get(Servicio, sid, populate_existing=True)
    detalle = (await client.get(f'/servicios/{sid}/acceso', headers=auth_catedra)).json()['acceso_ssh']
    assert detalle['direccion'] == servicio.acceso_metadata['addresses'][0]


async def test_al_iniciar_se_refresca_la_ip_y_un_fallo_no_rompe_nada(client, db, engine, proxmox, entorno,
        auth_catedra, auth_admin, catedra):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from uuid import uuid4
    from app.models.identidad_infraestructura import IdentidadInfraestructura
    from app.schemas.guest_runner import RunnerError
    from app.services import iaas_acceso_service
    _, sid = await _desplegado(client, db, engine, proxmox, auth_catedra, auth_admin, catedra,
        RunnerSsh(direccion='10.20.0.50'), nueva_clave())
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    servicio = await db.get(Servicio, sid, populate_existing=True)
    identidad = await db.get(IdentidadInfraestructura, servicio.identidad_infraestructura_id, populate_existing=True)
    nueva = await iaas_acceso_service.refrescar_direccion(sessions, runner=RunnerSsh(direccion='10.20.0.77'),
        identity=identidad, servicio_id=sid, operacion_id=uuid4())
    assert nueva == '10.20.0.77'
    assert (await client.get(f'/servicios/{sid}/acceso', headers=auth_catedra)).json()['acceso_ssh']['comando'] == 'ssh nap@10.20.0.77'
    # El nodo no responde: se conserva la última conocida y no se propaga la excepción.
    assert await iaas_acceso_service.refrescar_direccion(sessions, runner=RunnerSsh(excepcion=RunnerError('UNCONFIRMED')),
        identity=identidad, servicio_id=sid, operacion_id=uuid4()) is None
    assert (await client.get(f'/servicios/{sid}/acceso', headers=auth_catedra)).json()['acceso_ssh']['direccion'] == '10.20.0.77'
