from datetime import timedelta
from uuid import uuid4
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from app.models.ensayo_preparacion import EnsayoPreparacion
from app.models.definicion_servicio import DefinicionServicio
from app.models.incorporacion_aplicacion import IncorporacionAplicacion
from app.models.evento_ensayo import EventoEnsayo
from app.schemas.ensayo import DescartarEnsayo
from app.services import ensayo_service
from app.utils.clock import clock
from tests.fakes_biblioteca import DRAWIO


async def make_trial(db,admin):
    inc=IncorporacionAplicacion(**{k:DRAWIO[k] for k in ['identidad_externa','revision_fuente','comando_sha256','comando_origen','url_origen','nombre','descripcion','categorias','aliases']},origen_clave='test',creado_por=admin.id)
    db.add(inc);await db.flush()
    definition=DefinicionServicio(codigo='drawio-trial',version='1.0.0',producto='drawio',modelo_servicio='saas',manifest={})
    db.add(definition);await db.flush()
    trial=EnsayoPreparacion(incorporacion_id=inc.id,definicion_id=definition.id,perfil_id='prueba',creado_por=admin.id,
        expires_at=clock.now()+timedelta(hours=24),aviso_at=clock.now()+timedelta(hours=23))
    db.add(trial);await db.flush();return trial


async def test_descartar_cierra_generacion_sin_liberar_capacidad(db,admin):
    trial=await make_trial(db,admin)
    result=await ensayo_service.accion(db,trial.id,actor=admin,data=DescartarEnsayo(revision_esperada=1,motivo='No publicar'),clave='cerrar',action='descartar')
    assert result.status_code==202 and trial.execution_generation==2 and trial.cancelada_at
    assert trial.limpieza_estado=='pendiente' and trial.cierre_remoto_confirmado_at is None
    replay=await ensayo_service.accion(db,trial.id,actor=admin,data=DescartarEnsayo(revision_esperada=1,motivo='No publicar'),clave='cerrar',action='descartar')
    assert replay.replayed
    with pytest.raises(HTTPException):await ensayo_service.accion(db,trial.id,actor=admin,data=DescartarEnsayo(revision_esperada=2,motivo='Reabrir'),clave='no-reabrir',action='descartar')
    assert len((await db.scalars(select(EventoEnsayo))).all())==1


@pytest.mark.parametrize('state',['resolviendo','construyendo','ensayando','lista_para_comprobar','comprobada'])
async def test_vencimiento_cerca_todas_las_fases_sin_liberar_reservas(db,admin,monkeypatch,state):
    from unittest.mock import AsyncMock
    from app.services import ensayo_cleanup_service
    from app.models.recurso_ensayo import RecursoEnsayo
    from app.models.compromiso_capacidad import CompromisoCapacidad
    from app.models.notificacion import Notificacion
    trial=await make_trial(db,admin);trial.estado=state
    trial.aviso_at=clock.now()-timedelta(hours=2);trial.expires_at=clock.now()-timedelta(hours=1)
    resource=RecursoEnsayo(ensayo_id=trial.id,rol='funcional_a',destino_snapshot={});db.add(resource);await db.flush()
    ledger=CompromisoCapacidad(recurso_ensayo_id=resource.id,nodo='pve1',storage_id='local-lvm',storage_scope='prueba',vcpus_retenidos=1,ram_mb_retenida=512,disk_bytes_retenidos=4*1024**3,estado='reservado')
    db.add(ledger);await db.commit()
    monkeypatch.setattr(ensayo_cleanup_service,'procesar',AsyncMock(return_value=False))
    await ensayo_cleanup_service.tick(db)
    await db.refresh(trial);await db.refresh(ledger)
    assert trial.estado=='vencida' and trial.execution_generation==2 and trial.cancelada_at
    assert trial.limpieza_estado=='pendiente' and trial.avisado_at
    assert ledger.vcpus_retenidos==1 and not ledger.liberado_at
    await ensayo_cleanup_service.tick(db)
    notices=(await db.scalars(select(Notificacion).where(Notificacion.evento_clave==f'ensayo:{trial.id}:aviso'))).all()
    assert {n.canal for n in notices}=={'portal','email'} and len(notices)==2
