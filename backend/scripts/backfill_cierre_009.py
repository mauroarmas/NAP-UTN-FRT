"""Preparar/revisar/aplicar backfill de copia con API/worker detenidos.

Sin --aplicar genera un plan privado sin cambios. La aplicación exige el mismo
plan, SHA revisado, operador y referencia de copia; revalida datos/propiedad.
Nunca modifica invitados ni habilita accesos. No pasar URLs/claves como argumentos.
"""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


async def execute(args):
    from app.config import get_settings,Settings
    # No escribir accidentalmente en el destino de demostración por defecto.
    settings=get_settings()
    if settings.database_url==Settings.model_fields['database_url'].default:
        raise ValueError('Configurar explícitamente una copia aislada')
    from scripts.validar_carga import load_private,write_private
    from app.database import engine,AsyncSessionLocal
    from app.services.backfill_cierre_service import planificar,aplicar
    engine.echo=False
    try:
        async with AsyncSessionLocal() as db:
            if args.aplicar:
                plan=load_private(args.plan)
                checksum=hashlib.sha256(json.dumps(plan,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
                if not args.sha256 or checksum!=args.sha256:
                    raise ValueError('El SHA no coincide con el plan revisado')
                result=await aplicar(db,plan,operador=args.operador or '',referencia=args.referencia or '')
                await db.commit()
                print(json.dumps(result,ensure_ascii=False,indent=2))
            else:
                if engine.dialect.name=='postgresql':
                    from sqlalchemy import text
                    await db.execute(text('SET TRANSACTION READ ONLY'))
                plan=await planificar(db,sondear=args.sondear)
                write_private(args.plan,plan)
                await db.rollback()
                checksum=hashlib.sha256(json.dumps(plan,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
                print(json.dumps({'estado':'plan_sin_cambios','pasos':len(plan['pasos']),
                    'sha256_plan':checksum,'accion_siguiente':'Revisar acciones/pendientes y confirmar referencia de copia antes de --aplicar'},ensure_ascii=False,indent=2))
    finally: await engine.dispose()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',required=True,type=Path)
    parser.add_argument('--sondear',action='store_true',help='Consultar inventario PVE sin mutaciones al generar plan')
    parser.add_argument('--aplicar',action='store_true')
    parser.add_argument('--sha256',help='SHA canónico que imprimió el generador de plan')
    parser.add_argument('--operador')
    parser.add_argument('--referencia',help='Referencia institucional de copia/corte comprobado')
    args=parser.parse_args()
    if args.aplicar and (not args.sha256 or not args.operador or not args.referencia):
        parser.error('--aplicar requiere --sha256, --operador y --referencia')
    try: asyncio.run(execute(args))
    except Exception as exc:
        print(json.dumps({'estado':'no_aplicado','tipo':type(exc).__name__,
            'mensaje':'Revisar copia, esquema, claves y plan; no se imprimen datos sensibles'},ensure_ascii=False));return 1
    return 0


if __name__=='__main__': raise SystemExit(main())
