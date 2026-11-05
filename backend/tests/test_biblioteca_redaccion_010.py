import logging
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy import select
from app.services import ensayo_service,ensayo_worker
from app.models.operacion_ensayo import OperacionEnsayo
from tests.test_ensayo_limpieza_010 import make_trial
from tests.test_ensayo_worker_010 import config


async def test_error_remoto_no_filtra_cuerpo_comandos_ni_secretos(db,engine,admin,monkeypatch,caplog):
    config(monkeypatch);trial=await make_trial(db,admin)
    op=ensayo_service.enqueue(db,trial,kind='resolver',context={'recipe_revision':'a'*40,'input_ref':'catalogo','input_sha256':'b'*64})
    await db.commit()
    marker='Authorization: Bearer SECRET_TLS_PASSWORD shell-command'
    class Remote:
        async def execute(self,*args,**kwargs):raise ValueError(marker)
    with caplog.at_level(logging.INFO):await ensayo_worker.procesar_una(async_sessionmaker(engine,expire_on_commit=False),builder=Remote())
    assert marker not in caplog.text and 'SECRET_TLS_PASSWORD' not in caplog.text
    assert 'operation_id=' in caplog.text and 'error_type=ValueError' in caplog.text
    await db.refresh(op);await db.refresh(trial)
    assert marker not in str(ensayo_service.presentar(trial))
    assert op.error_codigo=='ejecucion_no_confirmada' and marker not in str(op.resultado)
