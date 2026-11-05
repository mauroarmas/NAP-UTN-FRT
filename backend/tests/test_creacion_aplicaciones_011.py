"""Short creation/recovery checks. No real PVE or external installers."""
from hashlib import sha256
from uuid import UUID,uuid4

import pytest
from sqlalchemy import select,update,func
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.consola_operacion import ConsolaOperacion,ConsolaFragmento
from app.models.intento_despliegue import IntentoDespliegue
from app.models.operacion_infraestructura import OperacionInfraestructura
from app.models.identidad_infraestructura import IdentidadInfraestructura
from app.models.servicio import Servicio
from app.utils.clock import clock
from app.utils.secretos import configured_keyring
from app.worker import procesar_una
from infra.applications.job.protocol import canonical,parse_request,public_identity,fingerprint
from tests.test_admision_aplicaciones_011 import (app_order,approve,perfil_capacidad,
    red_aplicaciones_011,profile_entry)


class Node:
    def __init__(self,app,sessions,*,lose_start=False,available=True):
        self.app,self.sessions=app,sessions
        self.lose_start,self.available=lose_start,available
        self.starts=[];self.requests=[];self.jobs={};self.boot=str(uuid4())

    async def execute(self,request,**kwargs):
        request=parse_request(canonical(request));action=request['action']
        self.requests.append(action)
        if action=='profiles':
            return {'protocol':request['protocol'],'ok':True,'action':action,'data':{'profiles':[
                {**self.app.document['perfil'],'estado':'habilitado','motivo_codigo':None}] if self.available else []}}
        if action=='start':
            async with self.sessions() as reader:
                attempt=await reader.scalar(select(IntentoDespliegue).where(IntentoDespliegue.execution_id==UUID(request['execution_id'])))
                op=await reader.get(OperacionInfraestructura,attempt.operacion_id)
                header=await reader.get(ConsolaOperacion,attempt.operacion_raiz_id)
                assert op.contexto_seguro['application_job_requested'] is True and header.last_seq>0
            self.starts.append(request['execution_id']);self.jobs[request['execution_id']]=fingerprint(request)
            if self.lose_start:
                self.lose_start=False;raise TimeoutError('response lost after accepting start')
        fp=self.jobs[request['execution_id']]
        return {'protocol':request['protocol'],'ok':True,'action':action,'data':{
            **public_identity(request),'estado':'ejecutando','fase':'instalacion','fingerprint':fp,
            'node_boot_id':self.boot,'last_source_seq':0,'acknowledged_seq':0,'resultado':None,'error_codigo':None}}


def stopped_create(proxmox):
    original=proxmox.create_lxc
    def create(node,**kwargs):
        result=original(node,**kwargs)
        if kwargs.get('start')==0:proxmox.estados[int(kwargs['vmid'])]='stopped'
        return result
    proxmox.create_lxc=create


async def wake(db):
    await db.execute(update(OperacionInfraestructura).values(next_poll_at=clock.now()))
    await db.commit();db.expire_all()


@pytest.mark.parametrize('lost',['none','create','start'])
async def test_create_is_stopped_and_takeover_never_duplicates_guest_or_installer(db,engine,admin,
        app_order,proxmox,lost):
    app=app_order;sessions=async_sessionmaker(engine,expire_on_commit=False)
    config_id=app.config.id
    await approve(db,admin,app,immediate=True)
    stopped_create(proxmox)
    node=Node(app,sessions,lose_start=lost=='start')
    lose_create=lost=='create'
    async def after_dispatch(lease,upid):
        nonlocal lose_create
        if lose_create:lose_create=False;raise RuntimeError('response lost after create')
    for _ in range(3):
        await procesar_una(sessions,pve=proxmox,runner=node,after_dispatch=after_dispatch)
        await wake(db)
    assert len(proxmox.creados)==1 and len(node.starts)==1
    create=proxmox.creados[0]
    assert create['start']==0 and create['onboot']==0 and create['unprivileged']==1
    assert ',firewall=1' in create['net0'] and not proxmox.iniciados
    identity=await db.scalar(select(IdentidadInfraestructura))
    nonce=configured_keyring().decrypt(identity.nonce_cifrado,context=f'infra:{identity.resource_uuid}:nonce')
    assert len(nonce)==64 and all(c in '0123456789abcdef' for c in nonce)
    assert sha256(nonce.encode()).hexdigest() in create['description'] and nonce not in create['description']
    attempt=await db.scalar(select(IntentoDespliegue));op=await db.scalar(select(OperacionInfraestructura))
    assert attempt.numero==1 and str(attempt.execution_id)==node.starts[0]
    assert op.intento>=3 and nonce not in str(op.contexto_seguro)
    assert await db.scalar(select(func.count()).select_from(IntentoDespliegue))==1
    service=await db.scalar(select(Servicio))
    assert service.configuracion_despliegue_id==config_id and service.disponibilidad_aplicacion!='utilizable'
    messages=list((await db.scalars(select(ConsolaFragmento))).all())
    assert messages and all(m.source=='portal' for m in messages)


async def test_unavailable_node_profile_blocks_creation_before_any_effect(db,engine,admin,app_order,proxmox):
    sessions=async_sessionmaker(engine,expire_on_commit=False)
    await approve(db,admin,app_order,immediate=True)
    node=Node(app_order,sessions,available=False)
    await procesar_una(sessions,pve=proxmox,runner=node)
    assert not proxmox.creados and not node.starts


async def test_failed_create_without_guest_preserves_console_and_releases_confirmed_absent_slot(db,engine,admin,app_order,proxmox):
    from app.models.reserva_red_aplicacion import ReservaRedAplicacion
    from app.models.compromiso_capacidad import CompromisoCapacidad
    sessions=async_sessionmaker(engine,expire_on_commit=False)
    await approve(db,admin,app_order,immediate=True)
    def fail(node,**kwargs):
        proxmox.creados.append({'node':node,**kwargs})
        upid=proxmox._task(node,kwargs['vmid'],'create')
        proxmox.configure_task(node,upid,[{'status':'stopped','exitstatus':'ERROR: allocation failed'}])
        return upid
    proxmox.create_lxc=fail;node=Node(app_order,sessions)
    await procesar_una(sessions,pve=proxmox,runner=node);db.expire_all()
    operation=await db.scalar(select(OperacionInfraestructura))
    identity=await db.scalar(select(IdentidadInfraestructura))
    allocation=await db.scalar(select(ReservaRedAplicacion))
    ledger=await db.scalar(select(CompromisoCapacidad))
    header=await db.get(ConsolaOperacion,operation.id)
    assert operation.estado=='fallida' and identity.ausencia_confirmada_at is not None
    assert allocation.liberada_at is not None and ledger.liberado_at is not None
    assert header.ultimo_resultado_seguro['hito']=='fallo' and header.last_seq>=2
    assert not node.starts
