"""Validaciones de arranque sin migraciones, semillas ni I/O de Proxmox."""
import os
from pathlib import Path

from sqlalchemy import text

from app.config import get_settings
from app.services.preflight_service import validar_configuracion,inspeccionar_claves,inspeccionar_ofertas


def exigir_configuracion():
    if os.getuid()==0: raise RuntimeError('El proceso operativo debe ejecutarse con UID no root')
    settings=get_settings()
    if not os.environ.get('NAP_SETTINGS_FILE'):
        raise RuntimeError('Producción requiere NAP_SETTINGS_FILE con configuración privada montada')
    report=validar_configuracion(settings)
    if not report['apto']:
        raise RuntimeError('Preflight operativo rechazado: '+', '.join(item['codigo'] for item in report['hallazgos']))
    return settings


def revision_esperada():
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    root=Path(__file__).resolve().parents[2]
    config=Config(str(root/'alembic.ini'))
    config.set_main_option('script_location',str(root/'alembic'))
    return ScriptDirectory.from_config(config).get_current_head()


async def exigir_rol_runtime(db):
    role=(await db.execute(text("""SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,
        has_schema_privilege(current_user,'public','CREATE') AS puede_ddl
        FROM pg_roles WHERE rolname=current_user"""))).mappings().one()
    if any(role.values()):
        raise RuntimeError('API/worker requieren rol runtime sin privilegios de propietario ni DDL')


async def comprobar_arranque(componente):
    if componente not in {'api','worker'}: raise ValueError('Componente desconocido')
    exigir_configuracion()
    from app.database import AsyncSessionLocal
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text('SET TRANSACTION READ ONLY'))
            await exigir_rol_runtime(db)
            versions=(await db.execute(text('SELECT version_num FROM alembic_version'))).scalars().all()
            if versions!=[revision_esperada()]:
                raise RuntimeError('Aplicar la migración release explícita; el arranque no cambia el esquema')
            from app.services.restauracion_service import exigir_habilitacion
            from fastapi import HTTPException
            try: await exigir_habilitacion(db, componente=componente)
            except HTTPException:
                raise RuntimeError('Restauración pendiente: completar preparación, ensayo y reconciliación antes del arranque') from None
            for check in [inspeccionar_claves,inspeccionar_ofertas]:
                result=await check(db)
                if not result['apto']: raise RuntimeError('Claves u ofertas pendientes de preflight; ejecutar preflight --datos')
            await db.rollback()
    except RuntimeError: raise
    except Exception:
        raise RuntimeError('No se pudo validar base/esquema/claves del arranque; no se imprimen credenciales') from None
