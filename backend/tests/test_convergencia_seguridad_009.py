"""Regresiones de convergencia; no prueban ACL ni sesiones PVE reales."""
import pytest
from fastapi import HTTPException
from sqlalchemy import select, func

from app.models.pedido import Pedido, EstadoPedido
from app.models.compromiso_capacidad import CompromisoCapacidad
from app.services import pedido_service
from tests import factories
from tests.capacity_helpers import materializado, perfil_capacidad  # noqa: F401


@pytest.mark.parametrize('flags', [{}, {'origen_sistema': True, 'operacion_nombrada': True}])
async def test_fachada_legacy_no_aprueba_sin_admision(db, catedra, admin, template, flags):
    pedido = await factories.crear_pedido(db, catedra.id, admin.id, template.id, estado=EstadoPedido.SOLICITADO)
    with pytest.raises(HTTPException) as exc:
        await pedido_service.cambiar_estado(db, pedido.id, 'aprobado', admin, **flags)
    assert exc.value.status_code == 405
    await db.refresh(pedido)
    assert pedido.estado == EstadoPedido.SOLICITADO
    assert await db.scalar(select(func.count()).select_from(CompromisoCapacidad)) == 0


async def test_fachada_legacy_no_cancela_como_docente(db, catedra, usuario_catedra, template):
    pedido = await factories.crear_pedido(db, catedra.id, usuario_catedra.id, template.id, estado=EstadoPedido.SOLICITADO)
    with pytest.raises(HTTPException) as exc:
        await pedido_service.cambiar_estado(db, pedido.id, 'cancelado', usuario_catedra)
    assert exc.value.status_code == 403
    await db.refresh(pedido)
    assert pedido.estado == EstadoPedido.SOLICITADO


async def test_archivo_del_laboratorio_no_habilita_consola(client, db, proxmox, perfil_capacidad,
        catedra, usuario_catedra, template, auth_catedra, monkeypatch):
    from app.models.servicio import EstadoServicio
    from app.config import get_settings
    servicio, _ = await materializado(db, proxmox, catedra, usuario_catedra, template)
    servicio.estado = EstadoServicio.RUNNING
    await db.commit()
    monkeypatch.setattr(get_settings(), 'console_access_profile', {}, raising=False)
    import os
    exists = os.path.exists
    monkeypatch.setattr(os.path, 'exists', lambda path: True
        if str(path).endswith('gate-revocacion-consola-t101.json') else exists(path))
    # Incluso si existe el viejo archivo de staging, no acredita esta instalación.
    response = await client.get(f'/servicios/{servicio.id}/consola', headers=auth_catedra)
    assert response.status_code == 409
    assert 'url' not in response.json()


async def test_pausa_confirmada_transiciona_pedido(db, engine, proxmox, perfil_capacidad,
        catedra, usuario_catedra, template):
    from uuid import uuid4
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.models.servicio import EstadoServicio
    from app.models.operacion_infraestructura import OperacionInfraestructura
    from app.services import operacion_service, orquestacion_service
    from app.services.identidad_infra_service import Propiedad
    from app.utils.clock import clock
    servicio, _ = await materializado(db, proxmox, catedra, usuario_catedra, template)
    servicio.estado = EstadoServicio.RUNNING
    op = OperacionInfraestructura(tipo='pausar', pedido_id=servicio.pedido_id, servicio_id=servicio.id,
        identidad_infraestructura_id=servicio.identidad_infraestructura_id, actor_tipo='sistema',
        actor_id_normalizado='vencimiento', idempotency_key='pausa-convergencia', request_hash='a'*64,
        estado='pendiente', fase='tarea', next_poll_at=clock.now(),
        contexto_seguro={'accion_externa': 'detener', 'asignacion': servicio.asignacion_snapshot})
    db.add(op)
    await db.commit()
    lease = await operacion_service.reclamar(db, owner=uuid4())
    await db.commit()
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await orquestacion_service._confirmed(sessions, lease, Propiedad('propia', 'test', status='stopped'))
    pedido = await db.get(Pedido, servicio.pedido_id, populate_existing=True)
    assert pedido.estado == EstadoPedido.SUSPENDIDO
    op2 = OperacionInfraestructura(tipo='iniciar', pedido_id=pedido.id, servicio_id=servicio.id,
        identidad_infraestructura_id=servicio.identidad_infraestructura_id, actor_tipo='usuario',
        actor_usuario_id=usuario_catedra.id, actor_id_normalizado=str(usuario_catedra.id),
        idempotency_key='inicio-convergencia', request_hash='b'*64, estado='pendiente', fase='tarea',
        next_poll_at=clock.now(), contexto_seguro={'accion_externa':'iniciar',
            'asignacion':servicio.asignacion_snapshot, 'destino':{'storage':'local-lvm'}})
    db.add(op2)
    await db.commit()
    lease2 = await operacion_service.reclamar(db, owner=uuid4())
    await db.commit()
    config = proxmox.configuraciones[('pve1',int(servicio.proxmox_vmid))]
    await orquestacion_service._confirmed(sessions,lease2,Propiedad('propia','test',config=config,status='running'))
    await db.refresh(pedido)
    assert pedido.estado == EstadoPedido.ACTIVO
    await db.refresh(servicio)
    assert servicio.disponibilidad_aplicacion == 'utilizable'


@pytest.mark.parametrize('unsent',[True,False])
async def test_cierre_error_solo_sin_efectos_pendientes(db,client,catedra,admin,template,auth_admin,unsent):
    from app.models.operacion_infraestructura import OperacionInfraestructura
    from app.utils.clock import clock
    request=await factories.crear_pedido(db,catedra.id,admin.id,template.id,estado=EstadoPedido.ERROR)
    db.add(OperacionInfraestructura(tipo='desplegar',pedido_id=request.id,actor_tipo='usuario',
        actor_id_normalizado=str(admin.id),idempotency_key='fallo-test',request_hash='a'*64,
        estado='fallida',fase='preparacion',contexto_seguro={},
        dispatch_started_at=None if unsent else clock.now()))
    await db.commit()
    result=await client.post(f'/pedidos/{request.id}/rechazar',headers=auth_admin|{'Idempotency-Key':'cerrar-error'},
        json={'motivo':'Cierre revisado sin efecto externo'})
    assert result.status_code==(200 if unsent else 409),result.text
    await db.refresh(request)
    assert request.estado==(EstadoPedido.RECHAZADO if unsent else EstadoPedido.ERROR)


async def console_fixture(db, actor, service, admin, monkeypatch, *, environment='real'):
    """Declaración sintética en DB efímera, sin acreditar un gate externo real."""
    from uuid import uuid4
    from datetime import timedelta
    import hashlib
    from app.config import get_settings
    from app.models.cambio_acceso_consola import CambioAccesoConsola
    from app.models.evidencia import Evidencia
    from app.schemas.evidencia import canonical
    from app.utils.clock import clock
    from tests.test_evidence_schema import document
    change_id, evidence_id = uuid4(), uuid4()
    actor.inventario_consola = 'asignada'
    actor.identidad_consola = actor.username + '@pve'
    actor.inventario_consola_actor, actor.inventario_consola_ref = 'test', 'TEST-ONLY'
    settings = get_settings()
    proof = document('revocacion_consola')
    proof.update(entorno=environment, observado_at=clock.now().isoformat().replace('+00:00', 'Z'))
    proof['resultado'].update(cambio_consola_id=str(change_id), identidad_nativa=actor.identidad_consola,
        cluster_uuid=settings.infrastructure_profile['cluster_id'], pve_version='9.2.2')
    raw = canonical(proof)
    evidence = Evidencia(id=evidence_id, tipo='revocacion_consola', documento_canonico=raw,
        sha256=hashlib.sha256(raw.encode()).hexdigest(), registrada_por=admin.id)
    db.add(evidence)
    await db.flush()
    db.add(CambioAccesoConsola(id=change_id, accion='reasignar', usuario_id=actor.id,
        revision_esperada=1, identidad_nativa=actor.identidad_consola, scopes_anteriores=[],
        scopes_propuestos=[], cambio_propuesto={'nombre':actor.nombre}, estado='completado',
        solicitada_por=admin.id, solicitada_at=clock.now()-timedelta(minutes=1),
        evidencia_id=evidence_id, completada_at=clock.now()))
    from app.models.catedra import Catedra
    category = await db.get(Catedra, service.catedra_id)
    profile = {'cluster_uuid':settings.infrastructure_profile['cluster_id'], 'pve_version':'9.2.2',
        'gate':{'evidencia_ref':str(evidence_id),'sha256':evidence.sha256},
        'identities':{actor.identidad_consola:{'usuario_id':actor.id,'revision_admin':actor.revision_admin,
            'referencia_institucional':'TEST-ONLY', 'catedras':{str(category.id):category.revision_admin}}}}
    monkeypatch.setattr(settings, 'console_access_profile', profile)
    await db.commit()
    return profile


@pytest.mark.parametrize('invalid', [None, 'cluster', 'checksum', 'user_revision', 'scope', 'unowned', 'simulation'])
async def test_consola_exige_prueba_instalacion_y_alcance_actual(db, client, proxmox, perfil_capacidad,
        catedra, usuario_catedra, template, admin, auth_catedra, monkeypatch, invalid):
    from app.models.servicio import EstadoServicio
    service, _ = await materializado(db, proxmox, catedra, usuario_catedra, template)
    service.estado = EstadoServicio.RUNNING
    profile = await console_fixture(db, usuario_catedra, service, admin, monkeypatch,
        environment='simulado' if invalid == 'simulation' else 'real')
    if invalid == 'cluster': profile['cluster_uuid'] = 'other'
    if invalid == 'checksum': profile['gate']['sha256'] = '0'*64
    if invalid == 'user_revision': profile['identities'][usuario_catedra.identidad_consola]['revision_admin'] += 1
    if invalid == 'scope': profile['identities'][usuario_catedra.identidad_consola]['catedras'] = {}
    if invalid == 'unowned':
        service.identidad_infraestructura_id = None
        await db.commit()
    response = await client.get(f'/servicios/{service.id}/consola', headers=auth_catedra)
    assert response.status_code == (200 if invalid is None else 409), response.text
