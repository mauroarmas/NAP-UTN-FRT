"""Presupuesto compartido por disco; primera admisión también se serializa."""
from sqlalchemy import select,func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from app.models.presupuesto_builder import PresupuestoBuilder
from app.models.reserva_espacio_builder import ReservaEspacioBuilder
from app.models.artefacto_preparado import ArtefactoPreparado
from app.utils.clock import clock
from app.utils.errors import error


async def bloquear(db,host):
    insert=pg_insert if db.bind.dialect.name=='postgresql' else sqlite_insert
    await db.execute(insert(PresupuestoBuilder).values(scope_id=host.scope_id,revision_config=host.revision,
        limite_bytes=host.limit_bytes,habilitado=True,updated_at=clock.now()).on_conflict_do_nothing(index_elements=['scope_id']))
    row=await db.scalar(select(PresupuestoBuilder).where(PresupuestoBuilder.scope_id==host.scope_id).with_for_update().execution_options(populate_existing=True))
    if not row.habilitado or row.revision_config!=host.revision or row.limite_bytes!=host.limit_bytes:
        raise error(409,'presupuesto_builder_cambiado','Revisá el presupuesto institucional antes de admitir trabajos')
    return row


async def reservar(db,*,ensayo_id,host_id,host,free_bytes):
    row=await bloquear(db,host)
    if type(free_bytes) is not int or free_bytes<0:raise error(502,'espacio_builder_no_verificable','No se pudo comprobar el espacio de construcción')
    existing=await db.scalar(select(ReservaEspacioBuilder).where(ReservaEspacioBuilder.ensayo_id==ensayo_id))
    if existing:return existing
    held=int(await db.scalar(select(func.coalesce(func.sum(ReservaEspacioBuilder.bytes_temporales+ReservaEspacioBuilder.bytes_finales_previstos),0)).where(ReservaEspacioBuilder.scope_id==host.scope_id,ReservaEspacioBuilder.liberado_at.is_(None))))
    retained=int(await db.scalar(select(func.coalesce(func.sum(ArtefactoPreparado.image_bytes+ArtefactoPreparado.bundle_bytes),0)).where(ArtefactoPreparado.scope_id==host.scope_id)))
    # Conservador: espacio físico observado y reservas aún no materializadas.
    if held+retained+host.job_bytes>row.limite_bytes or held+host.job_bytes>free_bytes:
        raise error(409,'espacio_builder_insuficiente','No hay presupuesto de disco para otro ensayo')
    reservation=ReservaEspacioBuilder(ensayo_id=ensayo_id,host_id=host_id,scope_id=host.scope_id,
        bytes_temporales=host.job_bytes,bytes_finales_previstos=0,estado='reservado')
    db.add(reservation);await db.flush();return reservation


async def liberar(db,*,ensayo_id,host,confirmado):
    await bloquear(db,host)
    row=await db.scalar(select(ReservaEspacioBuilder).where(ReservaEspacioBuilder.ensayo_id==ensayo_id).with_for_update())
    if not confirmado:raise error(409,'limpieza_no_confirmada','Conservar presupuesto hasta comprobar la limpieza')
    if row and row.liberado_at is None:
        row.bytes_temporales=row.bytes_finales_previstos=0
        row.estado='liberado';row.liberado_at=clock.now()
