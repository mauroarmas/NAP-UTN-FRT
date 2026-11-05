"""Alta inicial explícita e interactiva; nunca restablece cuentas existentes."""
import argparse
import asyncio
import getpass
import sys

from sqlalchemy import select, text

from app.database import AsyncSessionLocal
from app.models.usuario import Usuario, RolUsuario
from app.models.evento_seguridad import EventoSeguridad
from app.schemas.usuario import UsuarioCreate
from app.utils.security import hash_password_async


async def create_initial(db, *, username, nombre, email, password, actor):
    if not actor or not actor.strip() or len(actor) > 200:
        raise ValueError('Identificar al operador institucional')
    if db.bind.dialect.name == 'postgresql':
        await db.execute(text('SELECT pg_advisory_xact_lock(5002)'))
    if await db.scalar(select(Usuario.id).where(Usuario.rol == RolUsuario.ADMIN).limit(1)):
        raise ValueError('Ya existe un administrador; usar recuperación institucional')
    # El contrato de altas ordinarias no recibe contraseñas: el bootstrap
    # interactivo valida la suya al calcular el hash, fuera de ese DTO.
    values = UsuarioCreate(username=username, nombre=nombre, email=email, rol='admin')
    user = Usuario(username=values.username, nombre=values.nombre, email=values.email,
        password_hash=await hash_password_async(password), rol=RolUsuario.ADMIN, activo=True,
        debe_cambiar_password=True, totp_habilitado=False, inventario_consola='sin_identidad',
        inventario_consola_actor=actor, inventario_consola_ref='ALTA-INICIAL-SIN-CONCESION-NATIVA')
    db.add(user)
    await db.flush()
    db.add(EventoSeguridad(usuario_objetivo_id=user.id, actor_institucional=actor,
                          accion='bootstrap_admin', resultado='exitoso'))
    return user


async def _run(values):
    async with AsyncSessionLocal() as db, db.begin():
        await create_initial(db, **values)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--actor', default=getpass.getuser())
    args = parser.parse_args()
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print('El alta inicial requiere una terminal interactiva')
        return 2
    try:
        values = {'username': input('Usuario: '), 'nombre': input('Nombre: '), 'email': input('Email: '), 'actor': args.actor}
        values['password'] = getpass.getpass('Contraseña inicial: ')
        if values['password'] != getpass.getpass('Confirmar contraseña: '):
            raise ValueError('Confirmación diferente')
        asyncio.run(_run(values))
    except (ValueError, EOFError):
        print('Alta no realizada: revisar datos o usar recuperación si ya existe administración')
        return 2
    except Exception:
        print('Alta no realizada: revisar configuración y persistencia')
        return 1
    print('Administrador inicial creado. El primer ingreso requiere cambio de contraseña; 2FA es opcional.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
