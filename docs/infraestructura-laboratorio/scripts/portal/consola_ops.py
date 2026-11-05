"""Habilitación de la consola nativa en el portal del laboratorio, sin navegador. Corre DENTRO del contenedor api (ver consola.sh).

Usa los mismos servicios del backend que las pantallas de administración (inventario, trámite, evidencia, confirmación),
con sus mismas reglas y claves de idempotencia. Cuenta de administración: la cuenta semilla (NAP_ADMIN_EMAIL), que debe
estar activa mientras se opera (`portal.sh cuenta --activar` / `--desactivar`). Nada imprime secretos.

Orden del procedimiento:
  sintetico  -> inventario -> tramite -> (ensayo real de revocación) -> evidencia -> confirmar -> perfil
"""
import argparse
import asyncio
import json
import os
import sys

ADMIN_POR_DEFECTO = 'admin@utn.frt.edu.ar'
SINTETICO = 'consola-ensayo@lab.invalid'


def admin_email():
    return os.environ.get('NAP_ADMIN_EMAIL', ADMIN_POR_DEFECTO)


def build_parser():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('sintetico', help='Crea o desactiva la cuenta sintética que sostiene el trámite del ensayo')
    s.add_argument('--accion', choices=['crear', 'retirar'], required=True)
    i = sub.add_parser('inventario', help='Registra la identidad individual de una persona (importador institucional)')
    i.add_argument('--email', required=True); i.add_argument('--identidad', required=True)
    i.add_argument('--actor', required=True); i.add_argument('--referencia', required=True)
    t = sub.add_parser('tramite', help='Abre el trámite de retiro de acceso que acreditará el ensayo')
    t.add_argument('--email', default=SINTETICO); t.add_argument('--clave', required=True)
    e = sub.add_parser('evidencia', help='Registra la evidencia revocacion_consola a partir del informe del ensayo')
    e.add_argument('--cambio', required=True); e.add_argument('--informe', required=True)
    e.add_argument('--operador', required=True); e.add_argument('--referencia', required=True)
    e.add_argument('--pve-version', required=True); e.add_argument('--clave', required=True)
    c = sub.add_parser('confirmar', help='Completa el trámite con la evidencia registrada')
    c.add_argument('--cambio', required=True); c.add_argument('--evidencia', required=True); c.add_argument('--clave', required=True)
    f = sub.add_parser('perfil', help='Arma el console_access_profile a partir de la evidencia y las identidades inventariadas')
    f.add_argument('--evidencia', required=True); f.add_argument('--pve-version', required=True)
    f.add_argument('--nodos', required=True, help='JSON {"nodo": {"host": "...", "port": 8006}}')
    f.add_argument('--email', action='append', required=True, help='persona(s) a habilitar; repetible')
    f.add_argument('--salida', required=True)
    return p


async def _usuario(db, email):
    from sqlalchemy import select
    from app.models.usuario import Usuario
    user = await db.scalar(select(Usuario).where(Usuario.email == email))
    if user is None:
        sys.exit('no existe la cuenta ' + email)
    return user


async def _admin(db):
    user = await _usuario(db, admin_email())
    if not user.activo:
        sys.exit('la cuenta de administración está inactiva; activarla con portal.sh cuenta --activar')
    return user


async def _sintetico(a):
    import secrets
    from app.database import AsyncSessionLocal
    from app.models.usuario import Usuario, RolUsuario
    from app.utils.security import get_password_hash
    from sqlalchemy import select
    async with AsyncSessionLocal() as db:
        user = await db.scalar(select(Usuario).where(Usuario.email == SINTETICO))
        if a.accion == 'retirar':
            if user: user.activo = False
            await db.commit(); print('sintético desactivado'); return
        if user is None:   # contraseña aleatoria descartada: nadie inicia sesión con esta cuenta
            user = Usuario(username=SINTETICO.split('@')[0], email=SINTETICO, nombre='Ensayo de consola (laboratorio, sintético)',
                password_hash=get_password_hash(secrets.token_urlsafe(32)), rol=RolUsuario.CATEDRA_ADMIN, activo=True,
                recibir_notificaciones_email=False, inventario_consola='sin_identidad',
                inventario_consola_ref='LAB-SINTETICO', inventario_consola_actor='lab')
            db.add(user)
        user.activo = True
        await db.commit(); print('usuario sintético', user.id)


async def _inventario(a):
    from app.database import AsyncSessionLocal
    from scripts.importar_identidades_consola import apply_inventory, validate_inventory
    async with AsyncSessionLocal() as db:
        user = await _usuario(db, a.email)
        uid = user.id
    entries = validate_inventory([{'usuario_id': uid, 'estado': 'asignada', 'identidad': a.identidad}])
    await apply_inventory(entries, a.actor, a.referencia)
    print('inventario registrado para usuario', uid)


async def _tramite(a):
    from app.database import AsyncSessionLocal
    from app.services.consola_access_service import solicitar_cambio
    async with AsyncSessionLocal() as db:
        admin, user = await _admin(db), None
        user = await _usuario(db, a.email)
        resultado = await solicitar_cambio(db, usuario_objetivo_id=user.id, catedra_id=None, accion='desactivar',
            cambios={'activo': False}, revision_esperada=user.revision_admin, actor=admin, clave=a.clave)
        await db.commit()
    print('trámite', resultado.status_code, json.dumps(resultado.resultado))


async def _evidencia(a):
    from app.config import get_settings
    from app.database import AsyncSessionLocal
    from app.models.cambio_acceso_consola import CambioAccesoConsola
    from app.schemas.evidencia import canonical, parse_document
    from app.services import evidencia_service
    from uuid import UUID
    informe = json.load(open(a.informe))
    if not informe.get('aprobado'):
        sys.exit('el informe del ensayo no está aprobado; la consola debe permanecer cerrada (FR-008)')
    puntos = informe['puntos']
    async with AsyncSessionLocal() as db:
        admin = await _admin(db)
        change = await db.get(CambioAccesoConsola, UUID(a.cambio))
        if change is None:
            sys.exit('trámite inexistente')
        documento = {'schema_version': 1, 'tipo': 'revocacion_consola', 'entorno': 'real',
            'operador_institucional': a.operador, 'referencia_institucional': a.referencia,
            'observado_at': informe['finalizado_at'],
            'resultado': {'cambio_consola_id': str(change.id), 'revision_esperada': change.revision_esperada,
                'identidad_nativa': change.identidad_nativa, 'scopes_resultantes': sorted(change.scopes_propuestos),
                'sesiones_previas_terminadas': bool(puntos['1_sesion_abierta_termina']['ok']),
                'url_directa_denegada': bool(puntos['2_ticket_guardado_rechazado']['ok']),
                'otros_accesos_legitimos_comprobados': bool(puntos['3_otro_pool_conservado']['ok']),
                'cluster_uuid': get_settings().infrastructure_profile['cluster_id'], 'pve_version': a.pve_version}}
        resultado = await evidencia_service.registrar(db, parse_document(canonical(documento).encode()), usuario=admin, clave=a.clave)
        await db.commit()
    print('evidencia', resultado.status_code, json.dumps(resultado.resultado))


async def _confirmar(a):
    from uuid import UUID
    from app.database import AsyncSessionLocal
    from app.services.consola_access_service import confirmar
    async with AsyncSessionLocal() as db:
        admin = await _admin(db)
        resultado = await confirmar(db, UUID(a.cambio), UUID(a.evidencia), actor=admin, clave=a.clave)
        await db.commit()
    print('confirmación', resultado.status_code, json.dumps(resultado.resultado))


async def _perfil(a):
    from uuid import UUID
    from sqlalchemy import select
    from app.config import get_settings
    from app.database import AsyncSessionLocal
    from app.models.catedra import Catedra
    from app.models.evidencia import Evidencia
    from app.services.consola_destino_service import validar_nodos
    nodos = validar_nodos(json.loads(a.nodos))
    async with AsyncSessionLocal() as db:
        evidencia = await db.get(Evidencia, UUID(a.evidencia))
        if evidencia is None or evidencia.tipo != 'revocacion_consola':
            sys.exit('evidencia inexistente o de otro tipo')
        identidades = {}
        for email in a.email:
            user = await _usuario(db, email)
            if user.inventario_consola != 'asignada' or not user.identidad_consola:
                sys.exit(f'{email} no tiene identidad asignada en el inventario')
            propias = list((await db.scalars(select(Catedra).where(Catedra.titular_id == user.id, Catedra.activa.is_(True)))).all())
            identidades[user.identidad_consola] = {'usuario_id': user.id, 'revision_admin': user.revision_admin,
                'referencia_institucional': user.inventario_consola_ref,
                'catedras': {str(c.id): c.revision_admin for c in propias}}
    perfil = {'cluster_uuid': get_settings().infrastructure_profile['cluster_id'], 'pve_version': a.pve_version,
        'gate': {'evidencia_ref': a.evidencia, 'sha256': evidencia.sha256}, 'nodos': nodos, 'identities': identidades}
    fd = os.open(a.salida, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as fh:
        json.dump(perfil, fh, indent=2)
    print('perfil escrito en', a.salida, '| identidades:', len(identidades))


COMANDOS = {'sintetico': _sintetico, 'inventario': _inventario, 'tramite': _tramite,
            'evidencia': _evidencia, 'confirmar': _confirmar, 'perfil': _perfil}

if __name__ == '__main__':
    asyncio.run(COMANDOS[build_parser().parse_args().cmd](build_parser().parse_args()))
