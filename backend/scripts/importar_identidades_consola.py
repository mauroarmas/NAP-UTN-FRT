"""Importar inventario institucional comprobado, sin otorgar permisos PVE."""

import argparse
import asyncio
import json
import os
from pathlib import Path
import re

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.usuario import Usuario
from app.utils.clock import clock


def validate_inventory(value):
    if not isinstance(value, list) or not 1 <= len(value) <= 1000:
        raise ValueError('El inventario debe ser una lista acotada')
    ids, identities = set(), set()
    for row in value:
        if not isinstance(row, dict) or set(row) != {'usuario_id', 'estado', 'identidad'}:
            raise ValueError('Campos de inventario inválidos')
        if type(row['usuario_id']) is not int or row['usuario_id'] <= 0 or row['usuario_id'] in ids:
            raise ValueError('Usuario inválido o repetido')
        ids.add(row['usuario_id'])
        identity = row['identidad']
        if row['estado'] == 'sin_identidad' and identity is None:
            continue
        if (row['estado'] != 'asignada' or not isinstance(identity, str)
            or not re.fullmatch(r'[A-Za-z0-9._-]{1,100}@[A-Za-z0-9._-]{1,60}', identity)
            or identity.lower() == 'root@pam' or identity in identities):
            raise ValueError('Identidad individual inválida o repetida')
        identities.add(identity)
    return value


async def apply_inventory(entries, actor, reference):
    if not actor.strip() or not reference.strip() or len(actor) > 200 or len(reference) > 200:
        raise ValueError('Actor y referencia institucional son obligatorios')
    async with AsyncSessionLocal() as db, db.begin():
        for row in entries:
            user = await db.scalar(select(Usuario).where(Usuario.id == row['usuario_id']).with_for_update())
            if user is None:
                raise ValueError('Usuario no registrado')
            if user.inventario_consola == row['estado'] and user.identidad_consola == row['identidad']:
                continue
            if user.inventario_consola == 'asignada':
                raise ValueError('No se reemplaza una identidad asignada sin completar su revocación')
            user.identidad_consola, user.inventario_consola = row['identidad'], row['estado']
            user.inventario_consola_actor, user.inventario_consola_ref = actor, reference
            user.inventario_consola_historial = [*(user.inventario_consola_historial or []), {
                'actor': actor, 'referencia': reference, 'estado': row['estado'], 'identidad': row['identidad'],
                'registrada_at': clock.now().isoformat().replace('+00:00', 'Z'),
            }]
            user.revision_admin += 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archivo', required=True)
    parser.add_argument('--actor', required=True)
    parser.add_argument('--referencia', required=True)
    args = parser.parse_args()
    if not os.environ.get('DATABASE_URL'):
        parser.error('Configurar DATABASE_URL explícitamente; no se usa el destino por defecto')
    try:
        path = Path(args.archivo)
        if path.stat().st_size > 65536:
            raise ValueError('Archivo demasiado grande')
        entries = validate_inventory(json.loads(path.read_text()))
        asyncio.run(apply_inventory(entries, args.actor, args.referencia))
    except (ValueError, OSError):
        print('Inventario no importado: revisar formato, referencia y estado de identidades')
        return 2
    print('Inventario institucional registrado; no se modificaron permisos PVE')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
