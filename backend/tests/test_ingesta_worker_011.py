import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.consola_operacion import ConsolaOperacion,ConsolaFragmento
from app.models.intento_despliegue import IntentoDespliegue
from app.models.operacion_infraestructura import OperacionInfraestructura
from app.models.pedido import EstadoPedido,Pedido
from app.utils.clock import clock,db_utc
from app.worker import procesar_una,procesar_ingesta_una
from tests.test_creacion_aplicaciones_011 import (Node,stopped_create,wake,app_order,approve,
    perfil_capacidad,red_aplicaciones_011,profile_entry)
from tests.test_ingesta_consola_011 import console_job


class ConsoleNode(Node):
    state='ejecutando'
    lose_ack=False
    async def execute(self,request,**kwargs):
        reply=await super().execute(request,**kwargs)
        if request['action'] in {'read','ack'}:
            data=reply['data'];data.update(estado=self.state,last_source_seq=1,
                error_codigo='DEPENDENCY_UNAVAILABLE' if self.state=='fallido' else None)
            if request['action']=='read':
                data.update(dropped_ranges=[],items=[{'execution_id':request['execution_id'],
                    'source_seq':1,'captured_at':clock.now().isoformat().replace('+00:00','Z'),
                    'fase':'instalacion','stream':'sistema','texto_depurado':'Instalando aplicación.'}]
                    if request['after']<1 else [])
            else:
                data['acknowledged_seq']=request['through_seq']
                if self.lose_ack:
                    self.lose_ack=False;raise TimeoutError('ACK reply lost')
        return reply


@pytest.mark.parametrize('outcome',['ejecutando','fallido'])
async def test_worker_ingests_without_browser_and_never_restarts_job(db,engine,admin,app_order,proxmox,outcome,monkeypatch):
    app=app_order;sessions=async_sessionmaker(engine,expire_on_commit=False)
    pedido_id=app.pedido.id
    await approve(db,admin,app,immediate=True);stopped_create(proxmox)
    node=ConsoleNode(app,sessions)
    await procesar_una(sessions,pve=proxmox,runner=node)
    node.state=outcome
    node.lose_ack=outcome=='fallido'
    from datetime import timedelta
    now=clock.now();monkeypatch.setattr(clock,'now',lambda:now)
    for _ in range(2):
        now+=timedelta(seconds=2)
        await wake(db)
        await procesar_ingesta_una(sessions,runner=node)
    db.expire_all()
    attempt=await db.scalar(select(IntentoDespliegue));operation=await db.scalar(select(OperacionInfraestructura))
    header=await db.get(ConsolaOperacion,attempt.operacion_raiz_id)
    runner_rows=list((await db.scalars(select(ConsolaFragmento).where(ConsolaFragmento.source=='runner'))).all())
    assert attempt.ultimo_source_seq==1 and len(runner_rows)==1
    assert len(node.starts)==1 and 'read' in node.requests and 'ack' in node.requests
    pedido=await db.get(Pedido,pedido_id)
    if outcome=='fallido':
        assert operation.estado=='fallida' and pedido.estado==EstadoPedido.ERROR
        assert header.ultimo_resultado_seguro['hito']=='fallo'
        assert node.requests.count('ack')==2
        assert operation.contexto_seguro['application_console_ack_pending'] is False
    else:
        assert operation.estado=='en_curso' and pedido.estado==EstadoPedido.EN_DESPLIEGUE
        assert db_utc(header.last_ingested_at)>db_utc(header.last_captured_at)


async def test_periodic_purge_keeps_result_and_scheduler_uses_independent_cadences(db,console_job,monkeypatch):
    from datetime import timedelta
    from app import worker
    from app.services.consola_operacion_service import emitir_hito
    calls={}
    def register(name,callback,**kwargs):calls[name]=kwargs
    monkeypatch.setattr(worker.scheduler,'registrar',register)
    worker.registrar_trabajos()
    assert calls['ingerir_consolas']=={'cada_segundos':1}
    assert calls['procesar_operaciones']=={'cada_segundos':5}
    await emitir_hito(db,console_job.lease,hito='fallo');await db.commit()
    future=clock.now()+timedelta(days=31);monkeypatch.setattr(clock,'now',lambda:future)
    result=await worker.purgar_consolas(db)
    header=await db.get(ConsolaOperacion,console_job.lease.id)
    assert result['afectados']==1 and header.expired and header.last_seq==1
    assert header.ultimo_resultado_seguro['hito']=='fallo' and header.retained_bytes==0
