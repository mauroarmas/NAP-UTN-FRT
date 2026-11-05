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
