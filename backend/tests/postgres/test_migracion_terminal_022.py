"""Migración 022_01: identidades de consola y sesiones de terminal (feature 022)."""
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError

from app.database import Base
from tests.postgres.test_migracion_base_009 import migrate

TABLAS = ('identidades_consola', 'sesiones_terminal')
USUARIO = ("INSERT INTO usuarios (username,email,nombre,password_hash,rol,activo,totp_habilitado,created_at) "
           "VALUES ('{n}','{n}@x.test','U','h','CATEDRA_ADMIN',true,false,now())")


def bajar(connection, revision):
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / 'alembic.ini'))
    config.set_main_option('script_location', str(root / 'alembic'))
    config.attributes['connection'] = connection
    command.downgrade(config, revision)


async def test_upgrade_crea_las_tablas_con_el_esquema_de_los_modelos(empty_pg_schema):
    async with empty_pg_schema.begin() as conn:
        await conn.run_sync(lambda c: migrate(c, 'head'))
        assert await conn.scalar(text('SELECT version_num FROM alembic_version')) == '022_01_terminal_identidades'
        for tabla in TABLAS:
            columnas = await conn.run_sync(lambda c, t=tabla: {v['name'] for v in inspect(c).get_columns(t)})
            assert columnas == set(Base.metadata.tables[tabla].columns.keys())


async def test_restricciones_rechazan_estados_y_nombres_invalidos(empty_pg_schema):
    async with empty_pg_schema.begin() as conn:
        await conn.run_sync(lambda c: migrate(c, 'head'))
        await conn.execute(text(USUARIO.format(n='u22')))
        uid = await conn.scalar(text("SELECT id FROM usuarios WHERE username='u22'"))
    for nombre, estado in (('root@pam', 'lista'), ('nap-u1@pve', 'inventado'), ('nap-ux@pve', 'lista')):
        with pytest.raises(DBAPIError):
            async with empty_pg_schema.begin() as conn:
                await conn.execute(text("INSERT INTO identidades_consola (usuario_id,identidad,password_cifrada,estado,creada_at,actualizada_at) "
                    "VALUES (:u,:n,'x',:e,now(),now())"), {'u': uid, 'n': nombre, 'e': estado})


async def test_downgrade_revierte_si_estan_vacias_y_se_niega_si_hay_datos(empty_pg_schema):
    async with empty_pg_schema.begin() as conn:
        await conn.run_sync(lambda c: migrate(c, 'head'))
        await conn.run_sync(lambda c: bajar(c, '017_01_clave_acceso_servicio'))
        assert not await conn.run_sync(lambda c: any(inspect(c).has_table(t) for t in TABLAS))
        await conn.run_sync(lambda c: migrate(c, 'head'))
        await conn.execute(text(USUARIO.format(n='u22b')))
        uid = await conn.scalar(text("SELECT id FROM usuarios WHERE username='u22b'"))
        await conn.execute(text("INSERT INTO identidades_consola (usuario_id,identidad,password_cifrada,creada_at,actualizada_at) "
            f"VALUES ({uid},'nap-u{uid}@pve','x',now(),now())"))
    with pytest.raises(Exception):
        async with empty_pg_schema.begin() as conn:
            await conn.run_sync(lambda c: bajar(c, '017_01_clave_acceso_servicio'))
