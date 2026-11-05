"""Real row locks and shared-root retention; never connects to Proxmox."""
import asyncio
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
import pytest

from app.models.consola_operacion import ConsolaOperacion,ConsolaFragmento
from app.models.intento_despliegue import IntentoDespliegue
from app.models.operacion_infraestructura import OperacionInfraestructura
from app.services.consola_operacion_service import emitir_hito,ingerir
from app.services.operacion_service import LeaseOperacion
from app.utils.clock import clock
from tests.test_ingesta_consola_011 import console_job,batch
from tests.test_reserva_red_aplicacion_011 import new_identity_011


async def test_concurrent_portal_runner_replays_share_one_header_and_one_global_sequence(db,pg_sessions,console_job):
    job=console_job;page=batch(job);barrier=asyncio.Barrier(4)
    async def send(portal):
        async with pg_sessions() as session,session.begin():
            await barrier.wait()
            if portal:return await emitir_hito(session,job.lease,hito='creando_recurso')
            return await ingerir(session,job.lease,request=job.request,response=page)
    await asyncio.wait_for(asyncio.gather(send(True),send(False),send(True),send(False)),timeout=15)
    db.expire_all()
    rows=list((await db.scalars(select(ConsolaFragmento).order_by(ConsolaFragmento.seq))).all())
    header=await db.get(ConsolaOperacion,job.lease.id)
    assert [r.seq for r in rows]==[1,2,3] and header.next_seq==4
    assert sorted(r.source for r in rows)==['portal','runner','runner']
    assert len({(r.execution_id,r.source,r.source_key) for r in rows})==3


async def test_quota_is_shared_by_all_attempts_of_the_root_and_preserves_old_attempts(db,console_job,monkeypatch):
    from app.services import consola_operacion_service as service
    monkeypatch.setattr(service,'MAX_BYTES',60)
    job=console_job
    await ingerir(db,job.lease,request=job.request,response=batch(job))
    job.operation.estado='confirmada';await db.commit()
    identity=await new_identity_011(db,job.identity.cluster_id,502)
    owner=uuid4()
    operation=OperacionInfraestructura(tipo='desplegar',operacion_raiz_id=job.operation.id,
        identidad_infraestructura_id=identity.id,actor_tipo='sistema',actor_id_normalizado='fixture',
        idempotency_key=str(uuid4()),request_hash='a'*64,estado='en_curso',lease_owner=owner,
        lease_generation=1,lease_until=clock.now()+timedelta(minutes=2),contexto_seguro={'job_fingerprint':'f'*64})
    db.add(operation);await db.flush()
    attempt=IntentoDespliegue(operacion_id=operation.id,operacion_raiz_id=job.operation.id,
        numero=2,identidad_infraestructura_id=identity.id,configuracion_sha256='b'*64)
    db.add(attempt);await db.flush()
    request={**job.request,'operation_id':str(operation.id),'intento_id':str(attempt.id),
        'execution_id':str(attempt.execution_id),'resource_uuid':str(identity.resource_uuid),
        'vmid':identity.vmid,'pool':identity.pool_catedra}
    next_job=SimpleNamespace(request=request,attempt=attempt,boot=job.boot)
    await ingerir(db,LeaseOperacion(operation.id,owner,1),request=request,response=batch(next_job));await db.commit()
    header=await db.get(ConsolaOperacion,job.operation.id)
    rows=list((await db.scalars(select(ConsolaFragmento).order_by(ConsolaFragmento.seq))).all())
    assert [r.seq for r in rows]==[3,4] and header.first_retained_seq==3 and header.last_seq==4
    assert header.retained_bytes<=60 and header.dropped_messages==2
    assert await db.get(IntentoDespliegue,job.attempt.id) is not None


async def test_identical_local_keys_are_distinct_between_producers_but_not_within_one_producer(db,console_job):
    job=console_job
    await ingerir(db,job.lease,request=job.request,response=batch(job));await db.commit()
    # Schema fixture: even an identical local key from a different producer
    # cannot collide. The service itself derives portal keys from closed events.
    row=ConsolaFragmento(operacion_raiz_id=job.operation.id,seq=3,intento_id=job.attempt.id,
        execution_id=job.attempt.execution_id,source='portal',source_key='1',source_seq=None,
        captured_at=clock.now(),ingested_at=clock.now(),fase='creacion',stream='sistema',
        texto_depurado='Hito seguro.',utf8_bytes=len('Hito seguro.'.encode()))
    db.add(row);await db.flush()
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            db.add(ConsolaFragmento(operacion_raiz_id=job.operation.id,seq=4,intento_id=job.attempt.id,
                execution_id=job.attempt.execution_id,source='portal',source_key='1',source_seq=None,
                captured_at=clock.now(),ingested_at=clock.now(),fase='creacion',stream='sistema',
                texto_depurado='Hito repetido.',utf8_bytes=len('Hito repetido.'.encode())))
            await db.flush()


async def test_purga_30_dias_preserva_cabecera_y_resultado_seguro(db, console_job):
    from app.services.consola_operacion_service import purgar, emitir_hito, RETENTION_DAYS
    job = console_job
    await emitir_hito(db, job.lease, hito="creando_recurso")
    await emitir_hito(db, job.lease, hito="fallo")
    await db.commit()

    # Simular fragmentos con fecha de captura de hace 35 días
    cutoff_old = clock.now() - timedelta(days=RETENTION_DAYS + 5)
    rows = list((await db.scalars(select(ConsolaFragmento).where(ConsolaFragmento.operacion_raiz_id == job.operation.id))).all())
    for r in rows:
        r.captured_at = cutoff_old
    await db.commit()

    # Ejecutar purga
    await purgar(db, job.operation.id)
    await db.commit()

    header = await db.get(ConsolaOperacion, job.operation.id)
    assert header.expired is True
    assert header.dropped_messages == len(rows)
    assert header.ultimo_resultado_seguro == {
        "hito": "fallo",
        "texto": "No se pudo completar el despliegue.",
    }
    remaining = list((await db.scalars(select(ConsolaFragmento).where(ConsolaFragmento.operacion_raiz_id == job.operation.id))).all())
    assert len(remaining) == 0


async def test_exportacion_concurrente_con_through_seq_fijado(db, pg_sessions, console_job):
    from app.services.consola_operacion_service import consultar
    admin_user = SimpleNamespace(rol="admin", id=1)
    job = console_job
    # Ingerir primeros 2 fragmentos (seq 1, 2)
    await ingerir(db, job.lease, request=job.request, response=batch(job, sequences=(1, 2)))
    await db.commit()

    frozen_seq = 2
    barrier = asyncio.Barrier(2)

    async def reader():
        async with pg_sessions() as session:
            await barrier.wait()
            res = await consultar(session, job.operation.id, usuario=admin_user, through_seq=frozen_seq)
            return res

    async def writer():
        async with pg_sessions() as session, session.begin():
            await barrier.wait()
            # En paralelo, emitir nuevo hito en el portal
            await emitir_hito(session, job.lease, hito="creando_recurso")

    results = await asyncio.gather(reader(), writer())
    export_result = results[0]
    # La exportación con through_seq=2 debe congelarse en seq 2 sin incluir fragmentos posteriores
    assert [it["seq"] for it in export_result["items"]] == [1, 2]
    assert all(it["seq"] <= frozen_seq for it in export_result["items"])

