from datetime import timedelta

from sqlalchemy import select,func

from app.models.compromiso_capacidad import CompromisoCapacidad
from app.models.operacion_infraestructura import OperacionInfraestructura
from app.utils.clock import clock
from tests.capacity_helpers import perfil_capacidad  # noqa:F401
from tests.test_liberacion_009 import approved


async def test_deploy_projection_and_admission_use_ledger_expiry_not_retired_counter(
    client,db,perfil_capacidad,catedra,usuario_catedra,template,auth_admin,
):
    request=await approved(client,db,catedra,usuario_catedra,template,auth_admin)
    identity=request.id
    ledger=await db.scalar(select(CompromisoCapacidad))
    detail=(await client.get(f'/pedidos/{identity}',headers=auth_admin)).json()
    assert detail['despliegue_habilitado']
    assert detail['compromiso_capacidad']['vcpus_retenidos']==request.asignacion_snapshot['vcpus']
    assert detail['compromiso_capacidad']['expira_at']
    assert not {'reserva_vcpus','reserva_ram_mb','reserva_disk_gb','reserva_expira_at'} & detail.keys()
    ledger.expira_at=clock.now()-timedelta(seconds=1)
    # Un atributo Python sin columna no puede habilitar ni retener capacidad.
    request.reserva_expira_at=clock.now()+timedelta(days=90)
    await db.commit()
    detail=(await client.get(f'/pedidos/{identity}',headers=auth_admin)).json()
    assert not detail['despliegue_habilitado']
    result=await client.post(f'/servicios/desplegar/{identity}',json={},headers=auth_admin|{'Idempotency-Key':'expired-authority'})
    assert result.status_code==409
    assert await db.scalar(select(func.count()).select_from(OperacionInfraestructura))==0
