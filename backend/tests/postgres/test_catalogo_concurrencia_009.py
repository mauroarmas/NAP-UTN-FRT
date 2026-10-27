import asyncio
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select, func

from app.models.compromiso_capacidad import CompromisoCapacidad
from app.models.pedido import Pedido
from app.models.usuario import Usuario
from app.services import admision_service, catalogo_service
from tests.capacity_helpers import perfil_capacidad
from tests.test_perfiles_definiciones_009 import published_linux, profile, dates


async def test_retirement_and_approval_serialize_without_changing_agreed_definition(client, db, pg_sessions,
        auth_admin, auth_catedra, admin, catedra, published_linux, proxmox):
    identity, _ = published_linux
    template = (await client.post('/templates/', json=profile(identity), headers=auth_admin)).json()
    created = await client.post('/pedidos/', json={'template_id': template['id'], 'modelo_servicio': 'iaas', 'vigencia': dates()},
        headers=auth_catedra | {'Idempotency-Key': 'race-request'})
    assert created.status_code == 201, created.text
    request_id, actor_id = created.json()['id'], admin.id
    selection = {'asignacion': {'template_id': template['id'], 'definicion_version_id': identity,
        'vcpus': 1, 'ram_mb': 512, 'disk_gb': 4}, 'vigencia': dates()}
    evaluation = await client.post(f'/pedidos/{request_id}/evaluacion', json=selection, headers=auth_admin)
    assert evaluation.status_code == 200, evaluation.text
    body = {**selection, 'capacidad_token': evaluation.json()['capacidad_token']}
    await db.commit()
    barrier = asyncio.Barrier(2)
    async def decide(action):
        async with pg_sessions() as session:
            actor = await session.get(Usuario, actor_id)
            await barrier.wait()
            try:
                if action == 'approve':
                    result = await admision_service.aprobar(session, request_id, actor=actor, payload=body, clave='race-approve', pve=proxmox)
                else:
                    result = await catalogo_service.transicionar(session, UUID(identity), actor=actor, accion='retirar',
                        payload={'motivo': 'Nueva versión'}, clave='race-retire')
                await session.commit()
                return result.status_code
            except HTTPException as exc:
                await session.rollback()
                return exc.status_code
    approved, retired = await asyncio.gather(decide('approve'), decide('retire'))
    assert retired == 200 and approved in {200, 422}
    request = await db.get(Pedido, request_id, populate_existing=True)
    count = await db.scalar(select(func.count()).select_from(CompromisoCapacidad))
    if approved == 200:
        assert count == 1 and request.estado.value == 'aprobado'
        assert request.asignacion_snapshot['definicion_version_id'] == identity
    else:
        assert count == 0 and request.estado.value == 'solicitado'
