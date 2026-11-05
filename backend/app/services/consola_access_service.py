"""Coordina revocación institucional y cambio local, sin administrar PVE."""

from uuid import UUID, uuid4

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, text, or_, func

from app.models.cambio_acceso_consola import CambioAccesoConsola
from app.models.catedra import Catedra
from app.models.usuario import Usuario, RolUsuario
from app.services.acceso_service import requiere_admin_actual
from app.services.evidencia_service import obtener as obtener_evidencia
from app.services.idempotencia_service import ejecutar, ResultadoDecision
from app.services.usuario_service import con_catedras
from app.utils.clock import clock, db_utc
from app.utils.errors import error

OPEN = ['pendiente', 'revocacion_fallida']
USER_FIELDS = {'rol', 'activo', 'nombre', 'email', 'recibir_notificaciones_email', 'catedra_ids'}
CATEGORY_FIELDS = {'titular_id', 'activa', 'nombre', 'descripcion'}


async def _admin_lock(db):
    if db.bind.dialect.name == 'postgresql':
        await db.execute(text('SELECT pg_advisory_xact_lock(5002)'))


async def _user(db, identity):
    value = await db.scalar(select(Usuario).where(Usuario.id == identity).with_for_update()
                            .execution_options(populate_existing=True))
    if value is None:
        raise error(404, 'usuario_no_encontrado', 'Usuario no encontrado')
    return value


async def _category(db, identity):
    value = await db.scalar(select(Catedra).where(Catedra.id == identity).with_for_update()
                            .execution_options(populate_existing=True))
    if value is None:
        raise error(404, 'catedra_no_encontrada', 'Cátedra no encontrada')
    return value


async def _admins_available(db):
    blocked = select(CambioAccesoConsola.usuario_id).where(
        CambioAccesoConsola.estado.in_(OPEN),
        or_(CambioAccesoConsola.accion.in_(['retirar', 'desactivar', 'cambiar_rol']),
            CambioAccesoConsola.catedra_id.is_(None)),
    )
    return set((await db.scalars(select(Usuario.id).where(
        Usuario.activo.is_(True), Usuario.rol == RolUsuario.ADMIN, ~Usuario.id.in_(blocked)))).all())


def _removes_admin(user, action, changes):
    return user.activo and user.rol == RolUsuario.ADMIN and (
        action in {'retirar', 'desactivar'} or changes.get('activo') is False
        or ('rol' in changes and changes['rol'] != RolUsuario.ADMIN.value))


async def _own_categories(db, user_id):
    return list((await db.scalars(select(Catedra).where(Catedra.titular_id == user_id)
                                 .order_by(Catedra.id))).all())


async def _proposed_scopes(db, user, category, changes, action):
    if action in {'retirar', 'desactivar'} or changes.get('activo') is False:
        return []
    role = changes.get('rol', user.rol.value)
    if role == 'admin':
        ids = set((await db.scalars(select(Catedra.id).where(Catedra.activa.is_(True)))).all())
    else:
        ids = {row.id for row in await _own_categories(db, user.id) if row.activa}
    if 'catedra_ids' in changes and role != 'admin':
        ids = set(changes['catedra_ids'])
    if category and (changes.get('titular_id', user.id) != user.id or changes.get('activa') is False):
        ids.discard(category.id)
    return [f'/pool/catedra-{identity}' for identity in sorted(ids)]


async def _validate_changes(db, user, category, action, changes):
    allowed = CATEGORY_FIELDS if category else USER_FIELDS
    if not changes or set(changes) - allowed:
        raise error(422, 'cambio_invalido', 'El trámite solo admite cambios administrativos definidos')
    if 'rol' in changes and changes['rol'] not in {'admin', 'catedra_admin'}:
        raise error(422, 'rol_invalido', 'Rol no válido')
    if not category and changes.get('email') and await db.scalar(select(Usuario.id).where(
        func.lower(Usuario.email) == changes['email'].casefold(), Usuario.id != user.id).limit(1)):
        raise error(409, 'email_en_uso', 'Otra cuenta ya utiliza ese correo')
    if category and changes.get('titular_id') is not None:
        recipient = await db.get(Usuario, changes['titular_id'])
        if recipient is None or not recipient.activo:
            raise error(422, 'titular_invalido', 'El nuevo titular debe ser una cuenta activa')
    if not category and (action in {'retirar', 'desactivar'} or changes.get('activo') is False):
        owned = await _own_categories(db, user.id)
        if owned:
            raise error(409, 'catedras_sin_responsable', 'Reasigná las cátedras antes de retirar esta cuenta',
                        catedras=[{'id': row.id, 'nombre': row.nombre} for row in owned])
    if 'catedra_ids' in changes:
        values = changes['catedra_ids']
        if not isinstance(values, list) or any(type(value) is not int for value in values) or len(values) != len(set(values)):
            raise error(422, 'catedras_invalidas', 'Indicá una lista de cátedras sin duplicados')
        for identity in values:
            row = await _category(db, identity)
            if row.titular_id not in {None, user.id}:
                raise error(409, 'catedra_ocupada', 'La cátedra ya tiene otro responsable')


async def _invalidate_sessions(db, user):
    # US2 añade sesiones revocables: la versión invalida también sesiones previas.
    # Hasta entonces, el trámite abierto ya bloquea todo acceso de dominio afectado.
    if hasattr(user, 'auth_version'):
        from app.services.auth_service import invalidar_todas
        await invalidar_todas(db, user)


async def _apply(db, user, category, changes, action):
    if category:
        for field, value in changes.items():
            setattr(category, field, value)
        category.revision_admin += 1
    else:
        if 'catedra_ids' in changes:
            wanted = set(changes['catedra_ids'])
            owned = {row.id: row for row in await _own_categories(db, user.id)}
            for identity in sorted(set(owned) | wanted):
                row = await _category(db, identity)
                row.titular_id = user.id if identity in wanted else None
                row.revision_admin += 1
        for field, value in changes.items():
            if field != 'catedra_ids':
                setattr(user, field, RolUsuario(value) if field == 'rol' else value)
        if action in {'retirar', 'desactivar'}:
            user.activo = False
        user.revision_admin += 1
        await _invalidate_sessions(db, user)
    await db.flush()


async def _snapshot(db, user, category, change):
    if category:
        owner = await db.get(Usuario, category.titular_id) if category.titular_id else None
        return jsonable_encoder({'id': category.id, 'nombre': category.nombre, 'descripcion': category.descripcion,
            'activa': category.activa, 'created_at': category.created_at, 'titular_id': category.titular_id,
            'revision_admin': category.revision_admin,
            'titular': {'id': owner.id, 'nombre': owner.nombre, 'username': owner.username} if owner else None,
            'cambio_consola_id': str(change.id)})
    snapshot = (await con_catedras(db, user)).model_dump(mode='json')
    snapshot.update(revision_admin=user.revision_admin, cambio_consola_id=str(change.id))
    if change.accion == 'retirar':
        snapshot.update(resultado='desactivado', mensaje='La cuenta quedó retirada conservando su historial')
    return snapshot


async def solicitar_cambio(db, *, usuario_objetivo_id, catedra_id, accion, cambios,
                          revision_esperada, actor, clave):
    actor = await requiere_admin_actual(db, actor)
    if accion not in {'reasignar', 'retirar', 'desactivar', 'cambiar_rol'}:
        raise error(422, 'accion_invalida', 'Acción no admitida')

    async def decide(session):
        await _admin_lock(session)
        await requiere_admin_actual(session, actor)
        user = await _user(session, usuario_objetivo_id)
        category = await _category(session, catedra_id) if catedra_id is not None else None
        revision = category.revision_admin if category else user.revision_admin
        if revision != revision_esperada:
            raise error(409, 'revision_desactualizada', 'Los permisos cambiaron; recargá y revisá la decisión')
        clauses = [CambioAccesoConsola.usuario_id == user.id]
        if category:
            clauses.append(CambioAccesoConsola.catedra_id == category.id)
            if category.titular_id != user.id:
                raise error(409, 'titular_desactualizado', 'El titular ya cambió')
        pending = await session.scalar(select(CambioAccesoConsola.id).where(
            CambioAccesoConsola.estado.in_(OPEN), or_(*clauses)).limit(1))
        if pending:
            raise error(409, 'cambio_en_curso', 'Ya hay un cambio de consola pendiente', cambio_consola_id=str(pending))
        if _removes_admin(user, accion, cambios) and not (await _admins_available(session) - {user.id}):
            raise error(409, 'ultimo_administrador', 'Debe conservarse al menos un administrador habilitado')
        await _validate_changes(session, user, category, accion, cambios)
        if user.inventario_consola not in {'asignada', 'sin_identidad'}:
            raise error(409, 'consola_no_inventariada', 'Infraestructura debe registrar la identidad de consola antes de retirar permisos')
        if user.inventario_consola == 'asignada' and not user.identidad_consola:
            raise error(409, 'inventario_inconsistente', 'La identidad institucional debe regularizarse')
        before = await _proposed_scopes(session, user, None, {}, 'reasignar')
        desired = await _proposed_scopes(session, user, category, cambios, accion)
        # Durante la revocación solo se conservan alcances ya autorizados.
        # Las concesiones nuevas son posteriores al cambio académico confirmado.
        proposed = sorted(set(before) & set(desired))
        change = CambioAccesoConsola(accion=accion, usuario_id=user.id,
            catedra_id=category.id if category else None, revision_esperada=revision,
            identidad_nativa=user.identidad_consola, scopes_anteriores=before, scopes_propuestos=proposed,
            cambio_propuesto=cambios, solicitada_por=actor.id)
        session.add(change)
        await session.flush()
        if user.inventario_consola == 'sin_identidad':
            await _apply(session, user, category, cambios, accion)
            change.estado = 'completado'
            change.completada_at = clock.now()
            return ResultadoDecision(200, await _snapshot(session, user, category, change))
        if category is None:
            await _invalidate_sessions(session, user)
        return ResultadoDecision(202, {'cambio_consola_id': str(change.id), 'estado': 'pendiente',
                                      'usuario_id': user.id, 'catedra_id': catedra_id})

    return await ejecutar(db, actor_id=actor.id, clave=clave, metodo='PATCH',
        ruta=f'/cambios-consola/{usuario_objetivo_id}/{catedra_id or "cuenta"}',
        payload={'accion': accion, 'cambios': cambios, 'revision_esperada': revision_esperada}, decidir=decide)


async def confirmar(db, identity, evidencia_ref, *, actor, clave):
    actor = await requiere_admin_actual(db, actor)

    async def decide(session):
        await _admin_lock(session)
        await requiere_admin_actual(session, actor)
        change = await session.scalar(select(CambioAccesoConsola).where(CambioAccesoConsola.id == identity)
                                      .with_for_update().execution_options(populate_existing=True))
        if change is None:
            raise error(404, 'cambio_no_encontrado', 'Trámite no encontrado')
        if change.estado not in OPEN:
            raise error(409, 'cambio_completado', 'El cambio ya está completado')
        user = await _user(session, change.usuario_id)
        category = await _category(session, change.catedra_id) if change.catedra_id else None
        revision = category.revision_admin if category else user.revision_admin
        if revision != change.revision_esperada:
            raise error(409, 'revision_desactualizada', 'Los permisos cambiaron durante la revocación')
        evidence, document = await obtener_evidencia(session, evidencia_ref, tipo='revocacion_consola', revalidar=True)
        if document['resultado']['cambio_consola_id'] != str(change.id):
            raise error(422, 'evidencia_incompatible', 'La evidencia pertenece a otro trámite')
        if _removes_admin(user, change.accion, change.cambio_propuesto) and not (await _admins_available(session) - {user.id}):
            raise error(409, 'ultimo_administrador', 'Debe conservarse al menos un administrador habilitado')
        await _validate_changes(session, user, category, change.accion, change.cambio_propuesto)
        before = await _proposed_scopes(session, user, None, {}, 'reasignar')
        desired = await _proposed_scopes(session, user, category, change.cambio_propuesto, change.accion)
        if change.identidad_nativa != user.identidad_consola or change.scopes_propuestos != sorted(set(before) & set(desired)):
            raise error(409, 'alcance_desactualizado', 'El alcance de permisos ya cambió; resolver el trámite vigente')
        await _apply(session, user, category, change.cambio_propuesto, change.accion)
        change.estado, change.evidencia_id, change.completada_at = 'completado', evidence.id, clock.now()
        return ResultadoDecision(200, {'cambio_consola_id': str(change.id), 'estado': 'completado',
                                      'evidencia_ref': str(evidence.id)})

    return await ejecutar(db, actor_id=actor.id, clave=clave, metodo='POST',
        ruta=f'/admin/cambios-consola/{identity}/confirmar-revocacion',
        payload={'evidencia_ref': str(evidencia_ref)}, decidir=decide)


async def registrar_fallo(db, identity, motivo, *, actor, clave):
    actor = await requiere_admin_actual(db, actor)
    if not motivo or not motivo.strip() or len(motivo) > 500:
        raise error(422, 'motivo_invalido', 'Indicá un motivo institucional breve, sin secretos')

    async def decide(session):
        change = await session.scalar(select(CambioAccesoConsola).where(CambioAccesoConsola.id == identity).with_for_update())
        if change is None:
            raise error(404, 'cambio_no_encontrado', 'Trámite no encontrado')
        if change.estado not in OPEN:
            raise error(409, 'cambio_completado', 'El cambio ya terminó')
        change.estado, change.ultimo_error_seguro = 'revocacion_fallida', motivo.strip()
        return ResultadoDecision(200, {'cambio_consola_id': str(change.id), 'estado': change.estado})

    return await ejecutar(db, actor_id=actor.id, clave=clave, metodo='POST',
        ruta=f'/admin/cambios-consola/{identity}/registrar-fallo', payload={'motivo': motivo}, decidir=decide)
