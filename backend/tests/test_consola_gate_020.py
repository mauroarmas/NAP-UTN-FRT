"""Compuerta de consola para todos los roles y destino por nodo (spec 020). Dobles; no prueban sesiones PVE reales."""
import pytest

from tests.capacity_helpers import materializado, perfil_capacidad  # noqa: F401
from tests.test_convergencia_seguridad_009 import console_fixture


async def _servicio(db, proxmox, catedra, usuario_catedra, template):
    from app.models.servicio import EstadoServicio
    service, _ = await materializado(db, proxmox, catedra, usuario_catedra, template)
    service.estado = EstadoServicio.RUNNING
    await db.commit()
    return service


async def test_administracion_tambien_exige_la_habilitacion_de_la_instalacion(
        client, db, proxmox, perfil_capacidad, catedra, usuario_catedra, template, auth_admin, monkeypatch):
    from app.config import get_settings
    service = await _servicio(db, proxmox, catedra, usuario_catedra, template)
    monkeypatch.setattr(get_settings(), 'console_access_profile', {}, raising=False)
    response = await client.get(f'/servicios/{service.id}/consola', headers=auth_admin)
    assert response.status_code == 409
    assert response.json()['detail']['codigo'] == 'consola_no_habilitada'
    assert 'url' not in response.text


async def test_administracion_con_instalacion_habilitada_recibe_el_destino(
        client, db, proxmox, perfil_capacidad, catedra, usuario_catedra, template, admin, auth_admin, monkeypatch):
    service = await _servicio(db, proxmox, catedra, usuario_catedra, template)
    await console_fixture(db, usuario_catedra, service, admin, monkeypatch)
    response = await client.get(f'/servicios/{service.id}/consola', headers=auth_admin)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['url'].startswith('https://pve1.test:8006/?console=lxc&xtermjs=1&')
    assert f"vmid={service.proxmox_vmid}&node=pve1" in body['url']
    assert set(body) == {'url', 'login_url', 'servicio_id', 'vmid', 'node'}
    assert body['login_url'] == 'https://pve1.test:8006/'


async def test_persona_habilitada_recibe_el_destino_del_nodo_del_contenedor(
        client, db, proxmox, perfil_capacidad, catedra, usuario_catedra, template, admin, auth_catedra, monkeypatch):
    service = await _servicio(db, proxmox, catedra, usuario_catedra, template)
    profile = await console_fixture(db, usuario_catedra, service, admin, monkeypatch)
    profile['nodos']['pve2'] = {'host': 'pve2.test', 'port': 8006}
    response = await client.get(f'/servicios/{service.id}/consola', headers=auth_catedra)
    assert response.status_code == 200, response.text
    assert response.json()['url'].startswith('https://pve1.test:8006/')


async def test_failover_cuando_el_nodo_del_contenedor_no_responde(
        client, db, proxmox, perfil_capacidad, catedra, usuario_catedra, template, admin, auth_catedra, monkeypatch):
    from app.services import consola_destino_service
    service = await _servicio(db, proxmox, catedra, usuario_catedra, template)
    profile = await console_fixture(db, usuario_catedra, service, admin, monkeypatch)
    profile['nodos']['pve2'] = {'host': 'pve2.test', 'port': 8006}

    async def responde(host, port):
        return host == 'pve2.test'
    monkeypatch.setattr(consola_destino_service, '_responde', responde)
    response = await client.get(f'/servicios/{service.id}/consola', headers=auth_catedra)
    assert response.status_code == 200, response.text
    assert response.json()['url'].startswith('https://pve2.test:8006/')
    assert 'node=pve1' in response.json()['url']
    assert response.json()['login_url'] == 'https://pve2.test:8006/'


async def test_sin_nodos_vivos_la_persona_recibe_503_claro(
        client, db, proxmox, perfil_capacidad, catedra, usuario_catedra, template, admin, auth_catedra, monkeypatch):
    from app.services import consola_destino_service
    service = await _servicio(db, proxmox, catedra, usuario_catedra, template)
    await console_fixture(db, usuario_catedra, service, admin, monkeypatch)

    async def nadie(host, port):
        return False
    monkeypatch.setattr(consola_destino_service, '_responde', nadie)
    response = await client.get(f'/servicios/{service.id}/consola', headers=auth_catedra)
    assert response.status_code == 503
    assert response.json()['detail']['codigo'] == 'consola_nodo_no_disponible'
    assert 'url' not in response.text and 'pve1.test' not in response.text


@pytest.mark.parametrize('rol', ['catedra', 'admin'])
async def test_perfil_sin_nodos_deja_la_consola_cerrada(
        client, db, proxmox, perfil_capacidad, catedra, usuario_catedra, template, admin,
        auth_catedra, auth_admin, monkeypatch, rol):
    service = await _servicio(db, proxmox, catedra, usuario_catedra, template)
    profile = await console_fixture(db, usuario_catedra, service, admin, monkeypatch)
    del profile['nodos']
    headers = auth_catedra if rol == 'catedra' else auth_admin
    response = await client.get(f'/servicios/{service.id}/consola', headers=headers)
    assert response.status_code == 409
    assert response.json()['detail']['codigo'] == 'consola_no_habilitada'
    assert 'url' not in response.text


# --- Feature 022: la identidad y su alcance salen de la base ---------------------------------------------------------

@pytest.mark.parametrize('cambio', ['sin_fila', 'en_preparacion', 'con_error', 'retirada', 'sin_pool', 'otro_pool'])
async def test_sin_identidad_lista_que_cubra_la_catedra_la_consola_sigue_cerrada(
        client, db, proxmox, perfil_capacidad, catedra, usuario_catedra, template, admin, auth_catedra, monkeypatch, cambio):
    from sqlalchemy import delete, select
    from app.models.identidad_consola import IdentidadConsola
    service = await _servicio(db, proxmox, catedra, usuario_catedra, template)
    await console_fixture(db, usuario_catedra, service, admin, monkeypatch)
    fila = await db.scalar(select(IdentidadConsola).where(IdentidadConsola.usuario_id == usuario_catedra.id))
    if cambio == 'sin_fila':
        await db.execute(delete(IdentidadConsola))
    elif cambio in {'en_preparacion', 'con_error', 'retirada'}:
        fila.estado = cambio
    elif cambio == 'sin_pool':
        fila.pools_aplicados = []
    else:
        fila.pools_aplicados = ['catedra-99999']
    await db.commit()
    respuesta = await client.get(f'/servicios/{service.id}/consola', headers=auth_catedra)
    assert respuesta.status_code == 409 and respuesta.json()['detail']['codigo'] == 'consola_no_habilitada'
    assert 'url' not in respuesta.text


async def test_si_la_persona_deja_de_poseer_la_catedra_se_cierra_aunque_el_permiso_siga_aplicado(
        client, db, proxmox, perfil_capacidad, catedra, usuario_catedra, template, admin, auth_catedra, monkeypatch):
    from app.models.catedra import Catedra
    service = await _servicio(db, proxmox, catedra, usuario_catedra, template)
    await console_fixture(db, usuario_catedra, service, admin, monkeypatch)
    assert (await client.get(f'/servicios/{service.id}/consola', headers=auth_catedra)).status_code == 200
    (await db.get(Catedra, catedra.id)).titular_id = None       # el reconciliador todavía no retiró el permiso
    await db.commit()
    respuesta = await client.get(f'/servicios/{service.id}/consola', headers=auth_catedra)
    assert respuesta.status_code in {403, 404, 409}
    assert 'url' not in respuesta.text
