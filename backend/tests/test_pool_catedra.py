import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.services.pool_catedra_service import asegurar, verificar
from app.models.operacion_infraestructura import OperacionInfraestructura
from app.models.compromiso_capacidad import CompromisoCapacidad
from app.models.servicio import Servicio
from app.utils.clock import clock
from tests.capacity_helpers import perfil_capacidad  # noqa: F401
from tests.test_operaciones_recuperacion import prepared_guest, queued  # noqa: F401


async def test_consulta_admin_no_crea_pool_y_docente_no_accede(client, catedra, auth_admin, auth_catedra, proxmox):
    url = f'/catedras/{catedra.id}/infraestructura'
    assert (await client.get(url, headers=auth_catedra)).status_code == 403
    response = await client.get(url, headers=auth_admin)
    assert response.status_code == 200, response.text
    assert response.json()['estado'] == 'sin_servicios'
    assert response.headers['cache-control'] == 'no-store'
    assert proxmox.pools_creados == []
    assert (await client.get('/catedras/999999/infraestructura', headers=auth_admin)).status_code == 404


async def test_crea_pool_determinista_y_reutiliza_sin_duplicar(db, catedra, proxmox):
    pool = f'catedra-{catedra.id}'
    assert (await asegurar(db, catedra.id, pve=proxmox))['estado'] == 'preparada'
    assert (await asegurar(db, catedra.id, pve=proxmox))['estado'] == 'preparada'
    assert proxmox.pools_creados == [pool]
    assert proxmox.creados == []


@pytest.mark.parametrize('members', [
    [{'type': 'lxc', 'vmid': 999, 'node': 'pve1'}],
    [{'type': 'lxc', 'vmid': [], 'node': 'pve1'}],
    [{'type': 'storage', 'storage': 'externo', 'node': 'pve1'}],
])
async def test_pool_existente_con_recursos_ajenos_se_conserva_y_bloquea(db, catedra, proxmox, members):
    pool = f'catedra-{catedra.id}'
    proxmox.pools[pool] = members.copy()
    result = await verificar(db, catedra.id, pve=proxmox)
    assert result['codigo'] == 'pool_miembros_sin_verificar'
    with pytest.raises(HTTPException) as exc:
        await asegurar(db, catedra.id, pve=proxmox)
    assert exc.value.status_code == 409
    assert proxmox.pools[pool] == members and proxmox.pools_creados == []


async def test_pool_sin_permisos_o_conexion_no_crea(db, catedra, proxmox, monkeypatch):
    proxmox.permisos_pool.pop('VM.Allocate')
    assert (await verificar(db, catedra.id, pve=proxmox))['codigo'] == 'pool_permisos_insuficientes'
    proxmox.permisos_pool['VM.Allocate'] = 1
    def fail(): raise RuntimeError('No disponible')
    monkeypatch.setattr(proxmox, 'list_pools', fail)
    assert (await verificar(db, catedra.id, pve=proxmox))['codigo'] == 'pool_no_verificable'
    assert proxmox.pools_creados == []


async def test_creacion_con_respuesta_perdida_reconcilia_el_mismo_pool(db, catedra, proxmox, monkeypatch):
    original = proxmox.create_pool
    def lost_response(name):
        original(name)
        raise TimeoutError('Respuesta perdida o creación concurrente')
    monkeypatch.setattr(proxmox, 'create_pool', lost_response)
    assert (await asegurar(db, catedra.id, pve=proxmox))['estado'] == 'preparada'
    assert proxmox.pools_creados == [f'catedra-{catedra.id}']


async def test_identidad_con_secreto_invalido_no_se_anuncia_como_preparada(db, catedra, usuario_catedra, template, proxmox, perfil_capacidad):
    from tests.capacity_helpers import materializado
    from app.models.identidad_infraestructura import IdentidadInfraestructura
    service, _ = await materializado(db, proxmox, catedra, usuario_catedra, template)
    identity = await db.get(IdentidadInfraestructura, service.identidad_infraestructura_id)
    identity.nonce_cifrado = 'dato-no-recuperable'
    await db.flush()
    proxmox.pools[f'catedra-{catedra.id}'] = []
    result = await verificar(db, catedra.id, pve=proxmox)
    assert result['estado'] == 'requiere_atencion' and result['codigo'] == 'pool_no_verificable'
    assert proxmox.pools_creados == []


async def test_despliegue_prepara_pool_antes_del_contenedor_y_reintenta_sin_duplicar(
    client, db, engine, proxmox, perfil_capacidad, prepared_guest, catedra, usuario_catedra, template, auth_admin, monkeypatch
):
    from datetime import timedelta
    from app.worker import procesar_una
    now = clock.now()
    monkeypatch.setattr(clock, 'now', lambda: now)
    await queued(client, db, catedra, usuario_catedra, template, auth_admin)
    proxmox.permisos_pool.pop('Pool.Allocate')
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await procesar_una(sessions, pve=proxmox)
    operation = await db.scalar(select(OperacionInfraestructura).execution_options(populate_existing=True))
    assert operation.estado in {'pendiente', 'en_curso'} and operation.error_codigo == 'pool_permisos_insuficientes'
    assert operation.identidad_infraestructura_id is None and proxmox.creados == []
    ledger = await db.scalar(select(CompromisoCapacidad))
    assert ledger.estado == 'reservado' and ledger.liberado_at is None
    proxmox.permisos_pool['Pool.Allocate'] = 1
    now += timedelta(seconds=31)
    await procesar_una(sessions, pve=proxmox)
    assert proxmox.pools_creados == [f'catedra-{catedra.id}']
    assert len(proxmox.creados) == 1
    service = await db.scalar(select(Servicio))
    assert service is not None
    assert (await verificar(db, catedra.id, pve=proxmox))['estado'] == 'preparada'
