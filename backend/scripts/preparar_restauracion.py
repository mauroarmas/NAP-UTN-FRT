"""Preparar una COPIA aislada, con API/worker/SMTP detenidos y claves recuperadas.

Por defecto informa sin cambios. NAP_SETTINGS_FILE debe identificar la copia y
su restauracion_referencia. Nunca recibe contraseñas, DSN ni claves por argv.
--evaluar sondea PVE sólo mediante lecturas; --habilitar exige prueba separada.
"""
import argparse
import asyncio
import getpass
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def execute(args):
    if not os.environ.get('NAP_SETTINGS_FILE'):
        raise ValueError('Montar configuración privada de la copia mediante NAP_SETTINGS_FILE')
    from app.config import get_settings, Settings
    from sqlalchemy import select, func, text
    from sqlalchemy.engine import make_url
    from app.database import engine, AsyncSessionLocal
    from app.models.usuario import Usuario
    from app.models.restauracion import Restauracion
    from app.services.restauracion_service import (preparar_restauracion, reemitir_acceso_inicial,
        evaluar_habilitacion, habilitar_restauracion, _sha)
    from app.services.preflight_service import inspeccionar_claves
    from app.services.puesta_servicio_service import revision_esperada
    from scripts.validar_carga import load_private, write_private
    settings = get_settings()
    url = make_url(settings.database_url)
    if (settings.database_url == Settings.model_fields['database_url'].default
            or engine.dialect.name != 'postgresql' or url.database != args.base_copia
            or not settings.restauracion_referencia or settings.restauracion_referencia != args.referencia):
        raise ValueError('Revisar base explícita y referencia de la copia aislada')
    engine.echo = False
    try:
        async with AsyncSessionLocal() as db:
            if not args.aplicar: await db.execute(text('SET TRANSACTION READ ONLY'))
            if await db.scalar(text('SELECT current_database()')) != args.base_copia:
                raise ValueError('La conexión no corresponde a la copia nombrada')
            if (await db.execute(text('SELECT version_num FROM alembic_version'))).scalars().all() != [revision_esperada()]:
                raise ValueError('Aplicar primero la migración explícita sobre la copia')
            if args.evaluar:
                result = await evaluar_habilitacion(db, args.referencia)
            elif args.habilitar:
                proof = load_private(args.prueba)
                if _sha(proof) != args.sha256: raise ValueError('El SHA no corresponde a la prueba revisada')
                if proof.get('referencia_corte') != args.referencia: raise ValueError('Prueba de otro corte')
                result = await habilitar_restauracion(db, operador=args.operador, prueba=proof)
            elif args.reemitir_inicial is not None:
                if not sys.stdin.isatty(): raise ValueError('Reemitir sólo en una terminal privada interactiva')
                password = getpass.getpass('Nueva contraseña inicial de la cuenta existente: ')
                if password != getpass.getpass('Repetir contraseña: '): raise ValueError('Las contraseñas no coinciden')
                await reemitir_acceso_inicial(db, args.reemitir_inicial, password,
                    operador=args.operador, referencia=args.referencia_identidad)
                del password
                result = {'estado': 'acceso_inicial_reemitido', 'usuario_id': args.reemitir_inicial,
                          'entrega': 'Entregar por canal institucional; no se envía correo antiguo ni se cambia MFA'}
            elif args.aplicar:
                result = await preparar_restauracion(db, operador=args.operador, referencia=args.referencia)
            else:
                keys = await inspeccionar_claves(db)
                result = {'estado': 'plan_sin_cambios', 'claves': keys,
                    'usuarios': await db.scalar(select(func.count()).select_from(Usuario)),
                    'accesos_iniciales': await db.scalar(select(func.count()).select_from(Usuario).where(Usuario.debe_cambiar_password)),
                    'restauracion_preparada': bool(await db.scalar(select(Restauracion.id).where(Restauracion.referencia == args.referencia))),
                    'accion_siguiente': 'Verificar aislamiento, detener procesos y revisar corte antes de --aplicar'}
            if args.aplicar: await db.commit()
            else: await db.rollback()
            if args.salida: write_private(args.salida, result)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 1 if args.evaluar and not result['apto'] else 0
    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-copia', required=True, help='Nombre explícito de la base separada, nunca una URL')
    parser.add_argument('--referencia', required=True, help='Referencia única de este corte restaurado')
    parser.add_argument('--operador')
    parser.add_argument('--aplicar', action='store_true')
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument('--evaluar', action='store_true', help='Informe de reconciliación con lecturas PVE')
    actions.add_argument('--habilitar', action='store_true')
    actions.add_argument('--reemitir-inicial', type=int, help='ID de cuenta inicial existente; identidad comprobada')
    parser.add_argument('--referencia-identidad')
    parser.add_argument('--prueba', type=Path, help='Atestación privada del ensayo separado, archivo propio 0600')
    parser.add_argument('--sha256', help='SHA canónico revisado de la atestación')
    parser.add_argument('--salida', type=Path, help='Informe nuevo 0600, nunca sobrescribe uno existente')
    args = parser.parse_args()
    if args.aplicar and not args.operador: parser.error('--aplicar requiere --operador')
    if args.aplicar and args.salida: parser.error('--salida corresponde a informes de sólo lectura')
    if args.evaluar and args.aplicar: parser.error('--evaluar es sólo lectura')
    if args.habilitar and (not args.aplicar or not args.prueba or not args.sha256):
        parser.error('--habilitar requiere --aplicar --prueba --sha256 --operador')
    if args.reemitir_inicial is not None and (not args.aplicar or not args.referencia_identidad or args.reemitir_inicial <= 0):
        parser.error('--reemitir-inicial requiere ID positivo, --aplicar --operador y --referencia-identidad')
    try: return asyncio.run(execute(args))
    except Exception as exc:
        print(json.dumps({'estado': 'no_habilitado', 'tipo': type(exc).__name__,
            'mensaje': 'Revisar copia, claves, referencia, prueba y reconciliación; no se imprimen entradas sensibles'}))
        return 1


if __name__ == '__main__': raise SystemExit(main())
