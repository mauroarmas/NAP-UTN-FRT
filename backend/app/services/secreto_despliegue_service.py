"""Valores por alta: cifrados, estables al reintentar y separados del catálogo.

No hace commit ni envía avisos. El llamador confirma secretos y referencias con
la decisión aprobada. Los valores sólo salen hacia dispatch privado o acceso
autorizado de una instancia utilizable; nunca son un esquema de lectura ordinario.
"""
import hmac
import re
import secrets

from sqlalchemy import select

from app.models.configuracion_despliegue import ConfiguracionDespliegue
from app.models.operacion_infraestructura import OperacionInfraestructura
from app.models.pedido import Pedido, TipoPedido, EstadoPedido
from app.models.secreto_despliegue import SecretoDespliegue
from app.models.servicio import Servicio
from app.schemas.configuracion_despliegue import validar_documento
from app.services.acceso_service import requiere_admin_actual, requiere_acceso_servicio
from app.services.operacion_service import condicion_lease
from app.utils.errors import error
from app.utils.secretos import configured_keyring, SecretError


def _conflict():
    return error(409, 'secretos_despliegue_no_disponibles', 'Los datos privados no coinciden con la asignación aprobada')


def _invalid():
    return error(422, 'secretos_despliegue_invalidos', 'Completá los datos privados requeridos para este pedido')


def _input(values):
    if type(values) is not dict or len(values) > 20: raise _invalid()
    for name, value in values.items():
        if (type(name) is not str or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,63}', name)
                or type(value) is not str or not value or '\x00' in value): raise _invalid()
        try:
            if len(value.encode('utf-8')) > 4096: raise _invalid()
        except UnicodeError:
            raise _invalid() from None
    return values


def _keyring():
    try: return configured_keyring()
    except SecretError:
        raise error(503, 'cifrado_no_disponible', 'No se pudo acceder al almacenamiento privado') from None


def huella_entrada(pedido_id, aportados, *, key_id=None):
    if type(pedido_id) is not int or pedido_id < 1: raise _invalid()
    try:
        return _keyring().fingerprint(_input(aportados), context=f'deployment-input:{pedido_id}', key_id=key_id)
    except SecretError:
        raise error(503, 'cifrado_no_disponible', 'No se pudo verificar la solicitud privada') from None


def _context(row):
    return f'deployment:{row.pedido_id}:{row.nombre}:{row.revision}'


def _refs(rows):
    return [{'id': str(r.id), 'nombre': r.nombre, 'revision': r.revision} for r in sorted(rows, key=lambda r: r.nombre)]


async def _rows(db, pedido, config):
    values = list((await db.scalars(select(SecretoDespliegue).where(
        SecretoDespliegue.pedido_id == pedido.id).order_by(SecretoDespliegue.nombre))).all())
    # No inferir otra revisión ni recuperar valores de una decisión diferente.
    if any(r.configuracion_id != config.id for r in values) or len({r.nombre for r in values}) != len(values):
        raise _conflict()
    return values


async def _config(db, pedido):
    config = await db.get(ConfiguracionDespliegue, pedido.configuracion_despliegue_id) if pedido.configuracion_despliegue_id else None
    if config is None: raise _conflict()
    return config, validar_documento(config.documento)


def _decrypt(rows):
    keyring = _keyring()
    try:
        values = {r.nombre: keyring.decrypt(r.valor_cifrado, context=_context(r)) for r in rows}
        return _input(values)
    except SecretError:
        raise error(503, 'cifrado_no_disponible', 'No se pudieron recuperar los datos privados autorizados') from None


async def asegurar(db, pedido_id, *, usuario, aportados=None, _decision_en_curso=False):
    # The private flag is used only inside the locked approval transaction,
    # after selection/token checks and before recording the approved history.
    # It is never a field accepted from the portal.
    await requiere_admin_actual(db, usuario)
    provided = _input({} if aportados is None else aportados)
    pedido = await db.scalar(select(Pedido).where(Pedido.id == pedido_id)
        .with_for_update().execution_options(populate_existing=True))
    if pedido is None or pedido.deleted_at is not None: raise error(404, 'pedido_no_encontrado', 'Pedido no encontrado')
    approval_in_progress=bool(_decision_en_curso and pedido.estado==EstadoPedido.SOLICITADO
        and pedido.revision_decision>0 and pedido.configuracion_despliegue_id
        and (pedido.asignacion_snapshot or {}).get('configuracion_sha256'))
    if not approval_in_progress and pedido.estado not in {EstadoPedido.APROBADO, EstadoPedido.EN_DESPLIEGUE, EstadoPedido.ERROR, EstadoPedido.ACTIVO}:
        raise _conflict()
    if pedido.tipo == TipoPedido.RENOVACION:
        service = await db.get(Servicio, pedido.servicio_id)
        original = await db.get(Pedido, service.pedido_id) if service and service.pedido_id else None
        if (not service or service.deleted_at is not None or original is None or original.tipo != TipoPedido.ALTA
                or service.catedra_id != pedido.catedra_id or service.configuracion_despliegue_id != original.configuracion_despliegue_id
                or provided): raise _conflict()
        config, document = await _config(db, original)
        rows = await _rows(db, original, config)
        if {r.nombre for r in rows} != {s['nombre'] for s in document['secretos']}: raise _conflict()
        return _refs(rows)
    config, document = await _config(db, pedido)
    if approval_in_progress and pedido.asignacion_snapshot['configuracion_sha256']!=config.sha256:raise _conflict()
    declarations = {s['nombre']: s for s in document['secretos']}
    allowed = {n for n, d in declarations.items() if d['modo'] == 'por_pedido'}
    if set(provided) - allowed: raise _invalid()
    rows = await _rows(db, pedido, config)
    by_name = {r.nombre: r for r in rows}
    if set(by_name) - set(declarations): raise _conflict()
    missing_inputs = {n for n in allowed if n not in by_name and n not in provided}
    if missing_inputs: raise _invalid()
    keyring = _keyring()
    # Comparar la repetición antes de insertar nada; un replay no cambia secretos.
    for name in set(provided) & set(by_name):
        row = by_name[name]
        try: current = keyring.decrypt(row.valor_cifrado, context=_context(row))
        except SecretError:
            raise error(503, 'cifrado_no_disponible', 'No se pudieron verificar los datos privados') from None
        if type(current) is not str or not hmac.compare_digest(current.encode('utf-8'), provided[name].encode('utf-8')):
            raise _conflict()
    for name, declaration in declarations.items():
        if name in by_name: continue
        generated = declaration['modo'] == 'generado'
        value = secrets.token_urlsafe(32) if generated else provided[name]
        row = SecretoDespliegue(pedido_id=pedido.id, configuracion_id=config.id, nombre=name,
            revision=1, origen='generado' if generated else 'aportado')
        row.valor_cifrado = keyring.encrypt(value, context=_context(row))
        db.add(row); rows.append(row)
    await db.flush()
    return _refs(rows)


async def revelar_acceso(db, servicio_id, *, usuario):
    service = await requiere_acceso_servicio(db, usuario, servicio_id)
    if service.disponibilidad_aplicacion != 'utilizable' or not service.pedido_id: raise _conflict()
    pedido = await db.get(Pedido, service.pedido_id)
    if not pedido or service.configuracion_despliegue_id != pedido.configuracion_despliegue_id: raise _conflict()
    config, document = await _config(db, pedido)
    rows = await _rows(db, pedido, config)
    if {r.nombre for r in rows} != {s['nombre'] for s in document['secretos']}: raise _conflict()
    return _decrypt(rows)


async def para_dispatch(db, lease):
    operation = await db.scalar(select(OperacionInfraestructura).where(*condicion_lease(lease))
        .with_for_update().execution_options(populate_existing=True))
    if operation is None or not operation.pedido_id or operation.tipo not in {'desplegar', 'reparar'}: raise _conflict()
    pedido = await db.get(Pedido, operation.pedido_id, populate_existing=True)
    if (pedido is None or pedido.tipo != TipoPedido.ALTA or pedido.deleted_at is not None
            or pedido.estado not in {EstadoPedido.APROBADO, EstadoPedido.EN_DESPLIEGUE, EstadoPedido.ERROR}): raise _conflict()
    config, document = await _config(db, pedido)
    rows = await _rows(db, pedido, config)
    snapshot = pedido.asignacion_snapshot or {}
    if (operation.contexto_seguro.get('configuracion_sha256') != config.sha256
            or snapshot.get('configuracion_sha256') != config.sha256 or snapshot.get('secretos') != _refs(rows)
            or {r.nombre for r in rows} != {s['nombre'] for s in document['secretos']}): raise _conflict()
    return _decrypt(rows)
