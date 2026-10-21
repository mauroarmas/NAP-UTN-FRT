"""Outbox durable: claim breve, SMTP fuera de transacción y resultado condicional."""
import asyncio
import json
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select, update, and_, or_

from app.models.notificacion import Notificacion
from app.models.usuario import Usuario
from app.services.idempotencia_service import safe_json
from app.utils.clock import clock, db_utc
from app.utils.secretos import configured_keyring


async def encolar_bienvenida(db, user, password):
    entry = Notificacion(evento_clave=f'bienvenida:{user.id}:{user.auth_version}',
        destinatario_usuario_id=user.id, destinatario_normalizado=f'usuario:{user.id}', canal='email',
        payload={'tipo': 'bienvenida', 'username': user.username, 'nombre': user.nombre},
        auth_version_objetivo=user.auth_version, secreto_expira_at=clock.now() + timedelta(hours=24),
        proximo_intento_at=clock.now())
    db.add(entry)
    await db.flush()
    keyring = configured_keyring()
    entry.destinatario_email_cifrado = keyring.encrypt(user.email, context=f'email:{entry.id}')
    entry.secreto_temporal_encrypted = keyring.encrypt(password, context=f'welcome:{entry.id}')
    return entry


async def cancelar_bienvenidas(db, user):
    await db.execute(update(Notificacion).where(Notificacion.destinatario_usuario_id == user.id,
        Notificacion.auth_version_objetivo.is_not(None), Notificacion.estado.in_(['pendiente', 'fallida', 'enviando']))
        .values(estado='cancelada', secreto_temporal_encrypted=None, ultimo_error='credencial_reemplazada',
                lease_owner=None, lease_hasta=None))


async def _claim(db):
    now = clock.now()
    entry = await db.scalar(select(Notificacion).where(Notificacion.canal == 'email', or_(
        and_(Notificacion.estado.in_(['pendiente', 'fallida']), Notificacion.proximo_intento_at <= now),
        and_(Notificacion.estado == 'enviando', Notificacion.lease_hasta <= now)))
        .order_by(Notificacion.proximo_intento_at, Notificacion.id).with_for_update(skip_locked=True).limit(1)
        .execution_options(populate_existing=True))
    if entry is None:
        await db.commit()
        return None
    entry.estado, entry.lease_owner, entry.lease_hasta = 'enviando', str(uuid4()), now + timedelta(seconds=60)
    entry.generation += 1
    entry.intentos += 1
    await db.commit()
    return entry


async def procesar_uno(db, *, sender=None):
    from app.services.email_service import despachar_email, construir_bienvenida
    from app.services.restauracion_service import exigir_habilitacion
    await exigir_habilitacion(db, componente='outbox')
    entry = await _claim(db)
    if entry is None:
        return False
    identity, owner, generation = entry.id, entry.lease_owner, entry.generation
    attempts = entry.intentos
    user = await db.get(Usuario, entry.destinatario_usuario_id, populate_existing=True)
    allowed = bool(user and user.activo and user.email)
    if entry.auth_version_objetivo is not None:
        allowed = bool(allowed and user.debe_cambiar_password and user.auth_version == entry.auth_version_objetivo
            and entry.secreto_temporal_encrypted and entry.secreto_expira_at and db_utc(entry.secreto_expira_at) > clock.now())
    else:
        allowed = bool(allowed and user.recibir_notificaciones_email)
    if allowed and entry.catedra_id is not None:
        from app.services.acceso_service import es_visible
        try:
            allowed = await es_visible(db, user, entry.catedra_id)
        except Exception:
            allowed = False
    state, safe_error = 'cancelada', 'destinatario_o_credencial_no_vigente'
    try:
        if allowed:
            keyring = configured_keyring()
            email = keyring.decrypt(entry.destinatario_email_cifrado, context=f'email:{identity}')
            if email != user.email:
                allowed = False
            elif entry.payload.get('tipo') == 'bienvenida':
                password = keyring.decrypt(entry.secreto_temporal_encrypted, context=f'welcome:{identity}')
                subject, plain, html = construir_bienvenida(entry.payload['nombre'], entry.payload['username'], password)
                del password
            else:
                payload = json.loads(safe_json(entry.payload))
                subject, plain, html = payload['asunto'], payload['texto'], payload['html']
        await db.commit()  # Nunca mantener el claim/lecturas abiertos durante SMTP.
        if allowed:
            await asyncio.to_thread(sender or despachar_email, [email], subject, plain, html,
                                    message_id=f'<nap-{identity}@nap.invalid>')
            state, safe_error = 'enviada', None
    except Exception:
        # Ni el texto de excepción SMTP ni el cuerpo se guardan o registran.
        await db.rollback()
        state, safe_error = 'fallida', 'entrega_no_confirmada'
    values = {'estado': state, 'ultimo_error': safe_error, 'lease_owner': None, 'lease_hasta': None}
    if state in {'enviada', 'cancelada'}:
        values['secreto_temporal_encrypted'] = None
        if state == 'enviada':
            values['enviada_at'] = clock.now()
    else:
        values['proximo_intento_at'] = clock.now() + timedelta(seconds=min(3600, 30 * 2 ** min(attempts - 1, 7)))
    await db.execute(update(Notificacion).where(Notificacion.id == identity, Notificacion.estado == 'enviando',
        Notificacion.lease_owner == owner, Notificacion.generation == generation).values(**values))
    await db.commit()
    return True


async def procesar_lote(session_factory, *, limit=20):
    for _ in range(limit):
        async with session_factory() as db:
            if not await procesar_uno(db):
                break


async def encolar_acceso_verificado(db, service, *, preparation_id):
    """Solo aviso y referencia, sin claves ni enlaces externos al producto."""
    from app.models.catedra import Catedra
    category = await db.get(Catedra, service.catedra_id)
    user = await db.get(Usuario, category.titular_id) if category and category.titular_id else None
    if not user or not user.activo:
        return
    event = f'acceso:{service.id}:{preparation_id}'
    text = f'El acceso al servicio #{service.id} fue comprobado desde la red prevista. Consultá el portal para ver el acceso inicial.'
    payload = {'tipo': 'acceso_verificado', 'servicio_id': service.id, 'asunto': 'Acceso a tu servicio verificado',
        'texto': text, 'html': '<p>' + text + '</p>'}
    safe_json(payload)
    for channel in ['portal'] + (['email'] if user.email and user.recibir_notificaciones_email else []):
        entry = Notificacion(evento_clave=event, destinatario_usuario_id=user.id,
            destinatario_normalizado=f'usuario:{user.id}', canal=channel, catedra_id=service.catedra_id,
            servicio_id=service.id, payload=payload, proximo_intento_at=clock.now())
        db.add(entry)
        await db.flush()
        if channel == 'email':
            entry.destinatario_email_cifrado = configured_keyring().encrypt(user.email, context=f'email:{entry.id}')


async def encolar_aviso_servicio(db, service, *, evento, tipo, asunto, texto, incluir_admin=False):
    """Aviso seguro y deduplicado, en la transacción del evento de negocio."""
    from html import escape
    from app.models.catedra import Catedra
    from app.models.usuario import RolUsuario
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    category = await db.get(Catedra, service.catedra_id)
    owner = category.titular_id if category else None
    query = select(Usuario).where(Usuario.activo.is_(True))
    query = query.where(or_(Usuario.id == owner, Usuario.rol == RolUsuario.ADMIN) if incluir_admin else Usuario.id == owner)
    payload = {'tipo': tipo, 'servicio_id': service.id, 'asunto': asunto, 'texto': texto,
        'html': '<p>' + escape(texto) + '</p>'}
    safe_json(payload)
    insert = pg_insert if db.bind.dialect.name == 'postgresql' else sqlite_insert
    for user in (await db.scalars(query)).all():
        for channel in ['portal'] + (['email'] if user.email and user.recibir_notificaciones_email else []):
            identity = await db.scalar(insert(Notificacion).values(evento_clave=evento,
                destinatario_usuario_id=user.id, destinatario_normalizado=f'usuario:{user.id}', canal=channel,
                catedra_id=service.catedra_id, servicio_id=service.id, payload=payload, proximo_intento_at=clock.now())
                .on_conflict_do_nothing(index_elements=['evento_clave','destinatario_normalizado','canal'])
                .returning(Notificacion.id))
            if identity and channel == 'email':
                entry = await db.get(Notificacion, identity)
                entry.destinatario_email_cifrado = configured_keyring().encrypt(user.email, context=f'email:{entry.id}')
    await db.flush()
