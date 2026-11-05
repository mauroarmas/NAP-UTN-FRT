"""Compatibilidad de migración: columnas antiguas fuera del modelo operativo.

Sólo preflight/backfill y regularización explícita leen estos campos. No hay
doble escritura ni creación de columnas desde la aplicación.
"""
from sqlalchemy import inspect,select,table,column,Integer,String,JSON,DateTime,update

FIELDS={
    'usuarios':{'totp_secret':String(64)},
    'servicios':{'credenciales_acceso':JSON()},
    'pedidos':{'reserva_vcpus':Integer(),'reserva_ram_mb':Integer(),'reserva_disk_gb':Integer(),'reserva_expira_at':DateTime()},
}


def valor(row,field):
    return getattr(row,'_legado_cierre',{}).get(field)


async def cargar(db,name,rows):
    if not rows: return
    fields=FIELDS[name]
    connection=await db.connection()
    present=await connection.run_sync(lambda c:{v['name'] for v in inspect(c).get_columns(name)})
    names=[field for field in fields if field in present]
    saved={}
    if names:
        source=table(name,column('id',Integer()),*[column(field,fields[field]) for field in names])
        result=await db.execute(select(source).where(source.c.id.in_([row.id for row in rows])))
        saved={r['id']:{field:r[field] for field in names} for r in result.mappings()}
    for row in rows: row._legado_cierre=saved.get(row.id,{})


async def limpiar(db,name,row,field):
    if field not in FIELDS[name]: raise ValueError('Campo de migración no permitido')
    if field not in getattr(row,'_legado_cierre',{}): return
    source=table(name,column('id',Integer()),column(field,FIELDS[name][field]))
    await db.execute(update(source).where(source.c.id==row.id).values({field:None}))
    row._legado_cierre[field]=None
