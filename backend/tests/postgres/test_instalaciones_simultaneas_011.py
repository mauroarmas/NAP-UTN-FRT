"""One PostgreSQL race for the node installation limit; no real PVE effects."""
import asyncio
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select,func,update

from app.models.identidad_infraestructura import IdentidadInfraestructura
from app.models.intento_despliegue import IntentoDespliegue
from app.models.operacion_infraestructura import OperacionInfraestructura
from app.models.pedido import EstadoPedido,ModeloServicio
from app.services.application_execution_service import enviar_o_consultar
from app.services.operacion_service import LeaseOperacion
from app.utils.clock import clock
from app.worker import procesar_una
from tests import factories
from tests.test_creacion_aplicaciones_011 import (Node,stopped_create,app_order,approve,
    perfil_capacidad,red_aplicaciones_011,profile_entry)


async def seed_active(db,cluster,number):
    identity=IdentidadInfraestructura(cluster_id=cluster,nodo='pve1',vmid=900+number,
        pool_catedra='fixture',nonce_cifrado='fixture-unused')
    db.add(identity);await db.flush()
    operation=OperacionInfraestructura(tipo='desplegar',identidad_infraestructura_id=identity.id,
        actor_tipo='sistema',actor_id_normalizado='fixture',idempotency_key=str(uuid4()),
        request_hash='a'*64,estado='incierta',next_poll_at=clock.now()+timedelta(days=10))
    db.add(operation);await db.flush()
    attempt=IntentoDespliegue(operacion_id=operation.id,operacion_raiz_id=operation.id,numero=1,
        identidad_infraestructura_id=identity.id,configuracion_sha256='a'*64,
        iniciado_at=clock.now(),estado='ejecutando')
    db.add(attempt);await db.flush();return attempt


async def test_parallel_dispatches_do_not_exceed_two_active_installations(db,pg_sessions,admin,
        app_order,proxmox,catedra,usuario_catedra):
    app=app_order;first_id=app.pedido.id
    await approve(db,admin,app,immediate=True,key='first-install')
    other=await factories.crear_pedido(db,catedra.id,usuario_catedra.id,app.template.id,
        estado=EstadoPedido.SOLICITADO,modelo_servicio=ModeloServicio.SAAS)
    second_id=other.id
    from types import SimpleNamespace
    second=SimpleNamespace(**{**vars(app),'pedido':other})
    await approve(db,admin,second,immediate=True,key='second-install')
    for number in (1,2):await seed_active(db,app.entry['definition']['cluster_uuid'],number)
    await db.commit();stopped_create(proxmox)
    node=Node(app,pg_sessions)
    for pedido_id in (first_id,second_id):
        await procesar_una(pg_sessions,pve=proxmox,runner=node)
        await db.execute(update(OperacionInfraestructura).where(OperacionInfraestructura.pedido_id==pedido_id)
            .values(next_poll_at=clock.now()+timedelta(days=1)))
        await db.commit()
    assert len(proxmox.creados)==2 and not node.starts
    # One old job finishes; two candidates now race for exactly one free slot.
    seeded=await db.scalar(select(IntentoDespliegue).where(IntentoDespliegue.estado=='ejecutando'))
    seeded.estado='confirmado'
    operations=list((await db.scalars(select(OperacionInfraestructura).where(
        OperacionInfraestructura.pedido_id.in_([first_id,second_id])))).all())
    leases=[]
    for operation in operations:
        owner=uuid4();operation.lease_owner=owner;operation.lease_generation+=1
        operation.lease_until=clock.now()+timedelta(minutes=1);operation.estado='en_curso'
        leases.append(LeaseOperacion(operation.id,owner,operation.lease_generation))
    await db.commit()
    await asyncio.wait_for(asyncio.gather(*(enviar_o_consultar(pg_sessions,lease,pve=proxmox,runner=node)
        for lease in leases)),timeout=15)
    active=await db.scalar(select(func.count()).select_from(IntentoDespliegue).where(
        IntentoDespliegue.iniciado_at.is_not(None),IntentoDespliegue.estado.in_(['preparado','ejecutando','incierto'])))
    assert len(node.starts)==1 and active==2
