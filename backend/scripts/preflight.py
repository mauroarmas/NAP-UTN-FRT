"""Informe operativo sin secretos. No migra, no siembra ni modifica infraestructura."""
import argparse
import asyncio
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


async def execute(with_data,with_inventory=False):
    from app.config import get_settings
    from app.services.preflight_service import (validar_configuracion, inspeccionar_datos,
        inspeccionar_claves, inspeccionar_ofertas, inspeccionar_infraestructura)
    result={'configuracion':validar_configuracion(get_settings())}
    if with_data:
        from app.database import engine, AsyncSessionLocal
        engine.echo=False
        try:
            async with AsyncSessionLocal() as db:
                if engine.dialect.name=='postgresql':
                    from sqlalchemy import text
                    await db.execute(text('SET TRANSACTION READ ONLY'))
                result['datos']=await inspeccionar_datos(db)
                result['claves']=await inspeccionar_claves(db)
                result['ofertas']=await inspeccionar_ofertas(db)
                if with_inventory:
                    if result['configuracion']['apto']:
                        result['infraestructura']=await inspeccionar_infraestructura(db)
                    else:
                        result['infraestructura']={'apto':False,'hallazgos':[{'codigo':'sondeo_sin_configuracion_apta',
                            'mensaje':'Corregir configuración TLS/credenciales/origen antes del sondeo externo'}]}
                await db.rollback()
        except Exception:
            result['datos']={'apto':False,'hallazgos':[{'codigo':'base_no_verificable',
                'mensaje':'No se pudo verificar la base; revisar conexión y revisión sin exponer credenciales'}]}
        finally: await engine.dispose()
    result['apto']=all(value['apto'] for value in result.values())
    print(json.dumps(result,indent=2,ensure_ascii=False))
    return 0 if result['apto'] else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--datos',action='store_true',help='Inspeccionar DB en transacción de sólo lectura')
    parser.add_argument('--inventario',action='store_true',help='Con --datos, sondear inventario PVE sin mutaciones')
    args=parser.parse_args()
    if args.inventario and not args.datos: parser.error('--inventario requiere --datos')
    try: code=asyncio.run(execute(args.datos,args.inventario))
    except Exception:
        print(json.dumps({'apto':False,'hallazgos':[{'codigo':'configuracion_no_verificable',
            'mensaje':'Revisar formato y presencia de configuración; no se imprimen sus valores'}]}));code=1
    raise SystemExit(code)


if __name__=='__main__': main()
