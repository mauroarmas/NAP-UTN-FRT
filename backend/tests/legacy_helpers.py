"""Columnas del esquema anterior, sólo en SQLite/PG aleatorios de las fixtures."""
from sqlalchemy import inspect,table,column,Integer,String,JSON,DateTime,update,select,text

TYPES={
    'usuarios':{'totp_secret':(String(64),'VARCHAR(64)')},
    'servicios':{'credenciales_acceso':(JSON(),'JSON')},
    'pedidos':{**{k:(Integer(),'INTEGER') for k in ['reserva_vcpus','reserva_ram_mb','reserva_disk_gb']},
        'reserva_expira_at':(DateTime(),'TIMESTAMP')},
}


async def guardar(db,name,identity,**values):
    fields=TYPES[name]
    if not set(values)<=fields.keys(): raise ValueError('Fixture desconocida')
    connection=await db.connection()
    present=await connection.run_sync(lambda c:{v['name'] for v in inspect(c).get_columns(name)})
    for field in values:
        if field not in present: await db.execute(text(f'ALTER TABLE {name} ADD COLUMN {field} {fields[field][1]}'))
    target=table(name,column('id',Integer()),*[column(k,fields[k][0]) for k in values])
    await db.execute(update(target).where(target.c.id==identity).values(values))


async def leer(db,name,identity,field):
    source=table(name,column('id',Integer()),column(field,TYPES[name][field][0]))
    return await db.scalar(select(source.c[field]).where(source.c.id==identity))
