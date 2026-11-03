"""Operación del portal sin navegador, para el laboratorio. Corre DENTRO del contenedor api (ver portal.sh).

Usa los mismos servicios del backend que los endpoints, con las mismas reglas de autorización y de capacidad; no
es una automatización de clics ni prueba el inicio de sesión de una persona. Cada subcomando imprime sólo datos no
secretos. Las claves de idempotencia son obligatorias: repetir un comando con la misma clave devuelve el mismo
resultado y no duplica nada.

Cuentas: las decisiones de administración se atribuyen a la cuenta semilla (NAP_ADMIN_EMAIL, por defecto
admin@utn.frt.edu.ar). Está inactiva por defecto: `cuenta --activar` la enciende para operar y `cuenta --desactivar`
la devuelve a su estado. Sólo acepta esa cuenta y las que terminan en @lab.invalid; nunca la cuenta de otra persona.
"""
import argparse
import asyncio
import json
import os
import sys

ADMIN_POR_DEFECTO = 'admin@utn.frt.edu.ar'
DOMINIO_SINTETICO = '@lab.invalid'
CATEDRA_SINTETICA = 'Laboratorio Aislamiento B (sintética)'
USUARIO_SINTETICO = 'lab-aislamiento-b' + DOMINIO_SINTETICO
ACCIONES_ORDEN = ('detener', 'reiniciar', 'iniciar', 'eliminar')


def admin_email():
    return os.environ.get('NAP_ADMIN_EMAIL', ADMIN_POR_DEFECTO)


def email_permitido_para_cuenta(email):
    """Sólo se enciende o apaga la cuenta semilla o una cuenta sintética de laboratorio."""
    return email == admin_email() or email.endswith(DOMINIO_SINTETICO)


def build_parser():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='cmd', required=True)

    c = sub.add_parser('cuenta', help='Enciende o apaga la cuenta semilla o una sintética (sólo el campo activo)')
    c.add_argument('--email', default=None)
    g = c.add_mutually_exclusive_group(required=True)
    g.add_argument('--activar', action='store_true'); g.add_argument('--desactivar', action='store_true')

    o = sub.add_parser('oferta', help='Actualiza la oferta de una aplicación al perfil vigente (el botón "Actualizar aplicación")')
    o.add_argument('--aplicacion', choices=sorted(APLICACIONES), default='mariadb')
    o.add_argument('--plantilla', type=int, default=None, help='por defecto, la plantilla de la aplicación elegida')
    o.add_argument('--clave', required=True)

    ped = sub.add_parser('pedido', help='Crea, evalúa y aprueba un pedido MariaDB (Medium) hacia un nodo')
    ped.add_argument('--usuario', required=True, help='titular de la cátedra que pide')
    ped.add_argument('--catedra', type=int, required=True); ped.add_argument('--nodo', required=True)
    ped.add_argument('--aplicacion', choices=sorted(APLICACIONES), default='mariadb')
    ped.add_argument('--plantilla', type=int, default=None, help='por defecto, la plantilla de la aplicación elegida')
    ped.add_argument('--storage', default='truenas')
    ped.add_argument('--dias', type=int, default=14); ped.add_argument('--clave', required=True,
        help='prefijo de las claves de idempotencia (se derivan -pedido y -aprobar)')
    ped.add_argument('--sin-aprobar', action='store_true', help='sólo crear y evaluar')

    ord_ = sub.add_parser('orden', help='Detener, reiniciar, iniciar o dar de baja un servicio')
    ord_.add_argument('--servicio', type=int, required=True); ord_.add_argument('--accion', choices=ACCIONES_ORDEN, required=True)
    ord_.add_argument('--usuario', required=True); ord_.add_argument('--clave', required=True)

    r = sub.add_parser('reparar', help='Reintenta un pedido en ERROR como intento nuevo sobre el mismo recurso (administración)')
    r.add_argument('--pedido', type=int, required=True); r.add_argument('--clave', required=True)
    r.add_argument('--motivo', default='Reparación operada desde el laboratorio')

    rv = sub.add_parser('revelar', help='Revela el acceso inicial como lo haría la cátedra; lo guarda en un archivo 0600')
    rv.add_argument('--servicio', type=int, required=True); rv.add_argument('--usuario', required=True)
    rv.add_argument('--salida', required=True, help='archivo JSON (modo 0600); la contraseña nunca se imprime')

    cap = sub.add_parser('capacidad', help='Desglose de capacidad de una evaluación (lectura)')
    cap.add_argument('--pedido', type=int, required=True); cap.add_argument('--nodo', required=True)
    cap.add_argument('--plantilla', type=int, default=23); cap.add_argument('--storage', default='truenas')

    s = sub.add_parser('catedra-sintetica', help='Crea o desactiva una cátedra y un usuario sintéticos para pruebas de aislamiento')
    s.add_argument('--accion', choices=('crear', 'retirar'), required=True)
    return p


def _vigencia(dias):
    from datetime import timedelta
    from zoneinfo import ZoneInfo
    from app.utils.clock import clock
    hoy = clock.now().astimezone(ZoneInfo('America/Argentina/Tucuman')).date()
    return {'tipo': 'personalizado', 'desde': hoy.isoformat(), 'hasta': (hoy + timedelta(days=dias)).isoformat()}


async def _usuario(db, email):
    from sqlalchemy import select
    from app.models.usuario import Usuario
    usuario = await db.scalar(select(Usuario).where(Usuario.email == email))
    if usuario is None:
        sys.exit('no existe la cuenta ' + email)
    return usuario


async def _cuenta(a):
    from sqlalchemy import select
    from app.database import AsyncSessionLocal
    from app.models.usuario import Usuario
    email = a.email or admin_email()
    if not email_permitido_para_cuenta(email):
        sys.exit('sólo se enciende o apaga la cuenta semilla (%s) o una cuenta %s' % (admin_email(), DOMINIO_SINTETICO))
    async with AsyncSessionLocal() as db:
        usuario = await db.scalar(select(Usuario).where(Usuario.email == email))
        if usuario is None:
            sys.exit('no existe la cuenta ' + email)
        usuario.activo = bool(a.activar)
        await db.commit()
        print('cuenta', email, 'activo =', usuario.activo)


# Aplicaciones que este script sabe ofrecer: plantilla del catálogo y modelo de servicio.
APLICACIONES = {'mariadb': {'plantilla': 23, 'modelo': 'paas'}, 'nginx': {'plantilla': 22, 'modelo': 'saas'}}


def _plantilla(a):
    return a.plantilla if a.plantilla is not None else APLICACIONES[a.aplicacion]['plantilla']


def _cuerpo_oferta(revision, aplicacion='mariadb'):
    from app.schemas.aplicacion import RevisarAplicacion
    if aplicacion == 'nginx':
        return RevisarAplicacion(origen='imagen_docker', imagen='docker.io/nginxinc/nginx-unprivileged:latest', puerto=8080,
            modelo_servicio='saas', variables={}, secretos=[], persistencia=[], ruta_salud='/', websocket=False,
            revision_esperada=revision)
    return RevisarAplicacion(origen='imagen_docker', imagen='docker.io/library/mariadb:11.4', puerto=3306, modelo_servicio='paas',
        variables={'MARIADB_DATABASE': 'catedra', 'MARIADB_USER': 'docente', 'MARIADB_ROOT_HOST': 'localhost'},
        secretos=[{'nombre': 'MARIADB_PASSWORD', 'etiqueta': 'Contraseña de la base', 'modo': 'generado'},
                  {'nombre': 'MARIADB_ROOT_PASSWORD', 'etiqueta': 'Administración interna', 'modo': 'generado'}],
        persistencia=['/var/lib/mysql'], ruta_salud='/', websocket=False, revision_esperada=revision)


async def _oferta(a):
    from app.database import AsyncSessionLocal
    from app.models.recurso_template import RecursoTemplate
    from app.services import configuracion_despliegue_service as catalog
    async with AsyncSessionLocal() as db:
        admin = await _usuario(db, admin_email())
        plantilla = await db.get(RecursoTemplate, _plantilla(a))
        r = await catalog.change(db, actor=admin, template_id=_plantilla(a), clave=a.clave,
                                 body=_cuerpo_oferta(plantilla.revision, a.aplicacion))
        await db.commit()
        print('oferta', r.status_code, {k: r.resultado.get(k) for k in ('id', 'oferta_disponible', 'configuracion_id', 'requiere_actualizar_perfil')})


async def _pedido(a):
    from app.database import AsyncSessionLocal
    from app.models.recurso_template import RecursoTemplate
    from app.schemas.pedido import PedidoCreate, PedidoEvaluacion, PedidoAprobar
    from app.services import solicitud_service, evaluacion_service, admision_service
    async with AsyncSessionLocal() as db:
        admin = await _usuario(db, admin_email()); titular = await _usuario(db, a.usuario)
        plantilla = await db.get(RecursoTemplate, _plantilla(a))
        vig = _vigencia(a.dias)
        creado = await solicitud_service.crear(db, actor=titular, clave=a.clave + '-pedido', payload=PedidoCreate.model_validate({
            'template_id': _plantilla(a), 'modelo_servicio': APLICACIONES[a.aplicacion]['modelo'], 'vigencia': vig, 'catedra_id': a.catedra,
            'descripcion_requerimientos': 'Pedido operado desde el laboratorio (%s)' % a.clave}))
        await db.commit()
        pid = creado.resultado.get('id') or creado.resultado.get('pedido_id')
        cuerpo = {'asignacion': {'template_id': _plantilla(a), 'vcpus': 2, 'ram_mb': 1024, 'disk_gb': 8, 'tamano': 'medium',
                                 'configuracion_despliegue_id': str(plantilla.configuracion_despliegue_id)},
                  'destino': {'nodo': a.nodo, 'storage': a.storage}, 'vigencia': vig}
        ev = await evaluacion_service.evaluar(db, pid, actor=admin, payload=PedidoEvaluacion.model_validate(cuerpo))
        await db.commit()
        print('pedido', pid, 'catedra', a.catedra, 'nodo', a.nodo, '| libre_despues', ev.get('libre_despues'))
        if ev.get('excede_capacidad'):
            sys.exit('NO se aprueba: excede la capacidad')
        if a.sin_aprobar:
            return
        ap = await admision_service.aprobar(db, pid, actor=admin, clave=a.clave + '-aprobar', payload=PedidoAprobar.model_validate({
            **cuerpo, 'capacidad_token': ev['capacidad_token'], 'desplegar_inmediatamente': True}))
        await db.commit()
        print('aprobacion', ap.resultado.get('estado'), ap.resultado.get('operation_id'))


async def _orden(a):
    from app.database import AsyncSessionLocal
    from app.services.operacion_service import admitir_orden
    from app.services.orquestacion_service import iniciar_servicio
    async with AsyncSessionLocal() as db:
        usuario = await _usuario(db, a.usuario)
        if a.accion == 'iniciar':
            r = await iniciar_servicio(db, a.servicio, usuario, clave=a.clave)
        else:
            tipo = {'detener': 'detener', 'reiniciar': 'reiniciar', 'eliminar': 'eliminar'}[a.accion]
            r = await admitir_orden(db, a.servicio, tipo=tipo, usuario=usuario, clave=a.clave)
        await db.commit()
        print(a.accion, r.resultado.get('operation_id'), r.resultado.get('estado'))


async def _reparar(a):
    from app.database import AsyncSessionLocal
    from app.services.orquestacion_service import reintentar_despliegue
    async with AsyncSessionLocal() as db:
        admin = await _usuario(db, admin_email())
        r = await reintentar_despliegue(db, a.pedido, admin, clave=a.clave, motivo=a.motivo)
        await db.commit()
        print(r.status_code, r.resultado.get('estado'), r.resultado.get('operation_id'))


async def _revelar(a):
    from fastapi import HTTPException
    from app.database import AsyncSessionLocal
    from app.services.service_access_service import revelar
    async with AsyncSessionLocal() as db:
        usuario = await _usuario(db, a.usuario)
        try:
            r = await revelar(db, actor=usuario, servicio_id=a.servicio)
            await db.commit()
        except HTTPException as e:
            codigo = e.detail.get('codigo') if isinstance(e.detail, dict) else None
            print('servicio %d como %s: DENEGADO http=%s codigo=%s' % (a.servicio, a.usuario.split('@')[0], e.status_code, codigo))
            return
    c = r['credenciales']
    os.umask(0o077)
    descriptor = os.open(a.salida, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, 'w') as destino:
        json.dump({'host': c.get('host'), 'puerto': c.get('puerto'), 'usuario': c['usuario'], 'base': c['base'],
                   'password': c['password'], 'ca': c.get('ca_pem')}, destino)
    print('servicio %d como %s: PERMITIDO host=%s puerto=%s usuario=%s base=%s -> %s' % (
        a.servicio, a.usuario.split('@')[0], c.get('host'), c.get('puerto'), c['usuario'], c['base'], a.salida))


async def _capacidad(a):
    from app.database import AsyncSessionLocal
    from app.models.recurso_template import RecursoTemplate
    from app.schemas.pedido import PedidoEvaluacion
    from app.services import evaluacion_service
    async with AsyncSessionLocal() as db:
        admin = await _usuario(db, admin_email())
        plantilla = await db.get(RecursoTemplate, a.plantilla)
        cuerpo = {'asignacion': {'template_id': a.plantilla, 'vcpus': 2, 'ram_mb': 1024, 'disk_gb': 8, 'tamano': 'medium',
                                 'configuracion_despliegue_id': str(plantilla.configuracion_despliegue_id)},
                  'destino': {'nodo': a.nodo, 'storage': a.storage}, 'vigencia': _vigencia(14)}
        ev = await evaluacion_service.evaluar(db, a.pedido, actor=admin, payload=PedidoEvaluacion.model_validate(cuerpo))
        lim = ev['limites']
        print({k: lim[k]['disk_gb'] for k in ('fisica', 'margen', 'desplegado', 'comprometido', 'libre')}, '| libre_antes', ev['libre_antes'],
              '| libre_despues', ev['libre_despues'], '| excede_capacidad', ev.get('excede_capacidad'))


async def _catedra_sintetica(a):
    import secrets
    from sqlalchemy import select
    from app.database import AsyncSessionLocal
    from app.models.catedra import Catedra
    from app.models.usuario import Usuario, RolUsuario
    from app.utils.security import get_password_hash
    async with AsyncSessionLocal() as db:
        usuario = await db.scalar(select(Usuario).where(Usuario.email == USUARIO_SINTETICO))
        catedra = await db.scalar(select(Catedra).where(Catedra.nombre == CATEDRA_SINTETICA))
        if a.accion == 'retirar':
            if usuario: usuario.activo = False
            if catedra: catedra.activa = False
            await db.commit(); print('sintéticos desactivados'); return
        if usuario is None:   # contraseña aleatoria que se descarta: nadie inicia sesión con esta cuenta
            usuario = Usuario(username=USUARIO_SINTETICO.split('@')[0], email=USUARIO_SINTETICO, nombre='Docente B (laboratorio, sintético)',
                password_hash=get_password_hash(secrets.token_urlsafe(32)), rol=RolUsuario.CATEDRA_ADMIN, activo=True,
                recibir_notificaciones_email=False, inventario_consola='sin_identidad',
                inventario_consola_ref='LAB-SINTETICO', inventario_consola_actor='lab')
            db.add(usuario); await db.flush()
        usuario.activo = True
        if catedra is None:
            catedra = Catedra(nombre=CATEDRA_SINTETICA, titular_id=usuario.id, activa=True); db.add(catedra); await db.flush()
        catedra.activa, catedra.titular_id = True, usuario.id
        await db.commit()
        print('usuario', usuario.id, usuario.email, '| catedra', catedra.id)


COMANDOS = {'cuenta': _cuenta, 'oferta': _oferta, 'pedido': _pedido, 'orden': _orden, 'reparar': _reparar,
            'revelar': _revelar, 'capacidad': _capacidad, 'catedra-sintetica': _catedra_sintetica}

if __name__ == '__main__':
    args = build_parser().parse_args()
    asyncio.run(COMANDOS[args.cmd](args))
