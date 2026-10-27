"""Emitir autorización asistida tras comprobar identidad por canal institucional."""
import argparse
import asyncio
from datetime import timedelta
import hashlib
import secrets
import sys

from sqlalchemy import select, update

from app.database import AsyncSessionLocal
from app.models.usuario import Usuario
from app.models.autenticacion import DesafioAutenticacion
from app.models.evento_seguridad import EventoSeguridad
from app.utils.clock import clock


async def emitir(db, *, usuario, actor, motivo, referencia):
    if any(not value.strip() or len(value) > limit for value, limit in [(actor, 200), (motivo, 500), (referencia, 200)]):
        raise ValueError('Actor, motivo y referencia institucional son obligatorios')
    user = await db.scalar(select(Usuario).where(Usuario.username == usuario).with_for_update())
    if not user or not user.activo or not user.totp_habilitado:
        raise ValueError('Requiere cuenta activa con segundo factor habilitado')
    await db.execute(update(DesafioAutenticacion).where(DesafioAutenticacion.usuario_id == user.id,
        DesafioAutenticacion.tipo == 'assisted_recovery', DesafioAutenticacion.consumido_at.is_(None),
        DesafioAutenticacion.revocado_at.is_(None)).values(revocado_at=clock.now()))
    token = secrets.token_urlsafe(32)
    db.add(DesafioAutenticacion(usuario_id=user.id, tipo='assisted_recovery',
        token_hash=hashlib.sha256(token.encode()).hexdigest(), creado_at=clock.now(), expira_at=clock.now() + timedelta(minutes=5),
        actor_institucional=actor, motivo=motivo, referencia=referencia))
    db.add(EventoSeguridad(usuario_objetivo_id=user.id, actor_institucional=actor,
        accion='2fa_recuperacion_asistida_emitida', resultado='exitoso', motivo=motivo, referencia=referencia))
    await db.flush()
    return token


async def _run(args):
    async with AsyncSessionLocal() as db, db.begin():
        return await emitir(db, **vars(args))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ['usuario', 'actor', 'motivo', 'referencia']:
        parser.add_argument('--' + field, required=True)
    args = parser.parse_args()
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print('La autorización solo se emite una vez en terminal interactiva, sin redirecciones')
        return 2
    try:
        token = asyncio.run(_run(args))
    except ValueError:
        print('Autorización no emitida: revisar cuenta y referencia institucional')
        return 2
    except Exception:
        print('Autorización no emitida: revisar configuración y persistencia')
        return 1
    print('Autorización de un uso, válida cinco minutos. Entregar por el canal de verificación:')
    print(token)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
