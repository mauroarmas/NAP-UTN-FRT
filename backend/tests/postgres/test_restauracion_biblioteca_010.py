from sqlalchemy import select
from app.services import restauracion_service,ensayo_service,ensayo_worker
from app.models.operacion_ensayo import OperacionEnsayo
from app.models.recurso_ensayo import RecursoEnsayo
from app.utils.secretos import configured_keyring
from tests.test_ensayo_limpieza_010 import make_trial
from tests.test_ensayo_worker_010 import config


async def test_copia_cerca_ensayos_y_conserva_origen_y_secretos(db,admin,monkeypatch):
    config(monkeypatch)
    trial=await make_trial(db,admin)
    resource=RecursoEnsayo(ensayo_id=trial.id,rol='funcional_a',destino_snapshot={})
    db.add(resource);await db.flush()
    resource.credenciales_encrypted=configured_keyring().encrypt({'access_password':'solo-prueba'},context=f'ensayo:{resource.id}:secretos')
    original=resource.credenciales_encrypted;inc=trial.incorporacion_id;generation=trial.execution_generation
    op=ensayo_service.enqueue(db,trial,kind='resolver',context={});await db.commit()
    result=await restauracion_service.preparar_restauracion(db,operador='Operador',referencia='Copia ensayo 010')
    await db.commit();await db.refresh(trial);await db.refresh(op);await db.refresh(resource)
    assert trial.cancelada_at and trial.execution_generation>generation
    assert trial.limpieza_estado=='fallida' and op.estado=='incierta'
    assert trial.incorporacion_id==inc and resource.credenciales_encrypted==original
    assert await ensayo_worker.claim(db,'worker-copia') is None
    assert result['resumen']['ensayos_cerrados']==1
