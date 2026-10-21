"""Restauración fuera de línea: revocación indivisible y habilitación explícita.

No restaura dumps, crea cuentas, desactiva factores ni modifica invitados.
API, worker y SMTP deben estar detenidos antes de preparar el corte.
"""
import hashlib
import json
from uuid import UUID

from sqlalchemy import select, update, text

from app.config import get_settings
from app.models.autenticacion import SesionAutenticacion, DesafioAutenticacion, CodigoRecuperacion
from app.models.notificacion import Notificacion
from app.models.restauracion import Restauracion, AccesoInicialRestaurado
from app.models.usuario import Usuario
from app.models.operacion_infraestructura import OperacionInfraestructura
from app.models.compromiso_capacidad import CompromisoCapacidad
from app.services.capacidad_service import bloqueo_capacidad
from app.utils.clock import clock
from app.utils.errors import error
from app.utils.secretos import configured_keyring, SecretError

OPEN = ('pendiente', 'en_curso', 'incierta')


def referencia_valida(value):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 200 or any(ord(c) < 32 for c in value):
        raise ValueError('Operador y referencias deben ser identificadores no vacíos, sin datos secretos')
    return value.strip()


async def _lock(db):
    # Siempre después de capacidad (4001); el lock dura hasta commit/rollback.
    if db.bind.dialect.name == 'postgresql':
        await db.execute(text('SELECT pg_advisory_xact_lock(5003)'))


def _presentar(row):
    return {'restauracion_id': str(row.id), 'referencia': row.referencia, 'estado': row.estado, 'resumen': row.resumen}


async def exigir_habilitacion(db, *, componente):
    if componente not in {'api', 'worker', 'outbox'}: raise ValueError('Componente desconocido')
    pending = await db.scalar(select(Restauracion.id).where(Restauracion.estado == 'pendiente').limit(1))
    external = get_settings().restauracion_referencia
    verified = not external or await db.scalar(select(Restauracion.id).where(
        Restauracion.referencia == external, Restauracion.estado == 'habilitada'))
    if pending or not verified:
        raise error(503, 'restauracion_pendiente', 'La copia restaurada requiere reconciliación y habilitación institucional')


async def exigir_acceso_reemitido(db, user):
    if await db.scalar(select(AccesoInicialRestaurado.id).where(
        AccesoInicialRestaurado.usuario_id == user.id, AccesoInicialRestaurado.reemitido_at.is_(None)).limit(1)):
        raise error(503, 'acceso_inicial_requiere_reemision',
                    'Administración debe entregar un nuevo acceso inicial después de la restauración')


async def registrar_reemision(db, user, *, operador, referencia):
    operador, referencia = referencia_valida(operador), referencia_valida(referencia)
    await db.execute(update(AccesoInicialRestaurado).where(AccesoInicialRestaurado.usuario_id == user.id,
        AccesoInicialRestaurado.reemitido_at.is_(None)).values(reemitido_at=clock.now(),
            reemitido_por=operador, referencia=referencia))


async def validar_password_reemision(db, user, password):
    from app.utils.security import verificar_password_async
    if await db.scalar(select(AccesoInicialRestaurado.id).where(
        AccesoInicialRestaurado.usuario_id == user.id, AccesoInicialRestaurado.reemitido_at.is_(None)).limit(1)):
        if await verificar_password_async(password, user.password_hash):
            raise error(409, 'password_restaurada_no_reutilizable', 'Entregar una contraseña nueva, distinta de la del corte')


async def reemitir_acceso_inicial(db, usuario_id, password, *, operador, referencia):
    """Recuperación autorizada de cuenta existente; entrega por canal institucional."""
    operador, referencia = referencia_valida(operador), referencia_valida(referencia)
    from app.utils.security import hash_password_async, verificar_password_async, validar_password
    from app.services.auth_service import invalidar_todas, auditar
    from app.services.notificacion_service import cancelar_bienvenidas
    validar_password(password)
    async with bloqueo_capacidad(db):
        await _lock(db)
        user = await db.scalar(select(Usuario).where(Usuario.id == usuario_id).with_for_update()
                               .execution_options(populate_existing=True))
        if not user or not user.activo or not user.debe_cambiar_password:
            raise error(409, 'cuenta_no_requiere_reemision', 'Revisar la cuenta existente y su identidad institucional')
        pending = await db.scalar(select(AccesoInicialRestaurado.id).where(
            AccesoInicialRestaurado.usuario_id == user.id, AccesoInicialRestaurado.reemitido_at.is_(None)))
        if not pending: raise error(409, 'cuenta_no_requiere_reemision', 'La cuenta no tiene una entrega restaurada pendiente')
        if await verificar_password_async(password, user.password_hash):
            raise ValueError('La nueva credencial debe ser distinta de la restaurada')
        user.password_hash = await hash_password_async(password)
        await cancelar_bienvenidas(db, user)
        await invalidar_todas(db, user)
        await registrar_reemision(db, user, operador=operador, referencia=referencia)
        auditar(db, user, 'acceso_restaurado_reemitido', motivo=operador, referencia=referencia)
        await db.flush()


async def preparar_restauracion(db, *, operador, referencia):
    operador, referencia = referencia_valida(operador), referencia_valida(referencia)
    external = get_settings().restauracion_referencia
    if external and external != referencia: raise ValueError('La referencia no coincide con la configuración de la copia')
    async with bloqueo_capacidad(db):
        await _lock(db)
        # Ninguna versión/hash/lease cambia si faltan claves, incluso en reintentos.
        configured_keyring()
        from app.services.preflight_service import inspeccionar_claves
        if not (await inspeccionar_claves(db))['apto']:
            raise SecretError('Recuperar todas las claves del corte antes de preparar la restauración')
        previous = await db.scalar(select(Restauracion).where(Restauracion.referencia == referencia).with_for_update())
        if previous:
            if previous.estado != 'pendiente':
                raise error(409, 'referencia_restauracion_utilizada', 'Usar una referencia nueva para cada restauración')
            return _presentar(previous)
        if await db.scalar(select(Restauracion.id).where(Restauracion.estado == 'pendiente')):
            raise error(409, 'otra_restauracion_pendiente', 'Resolver el corte preparado antes de cambiar su referencia')
        now = clock.now()
        row = Restauracion(referencia=referencia, operador=operador, preparada_at=now, estado='pendiente', resumen={})
        db.add(row); await db.flush()
        users = list((await db.scalars(select(Usuario).order_by(Usuario.id).with_for_update()
                                      .execution_options(populate_existing=True))).all())
        initial = 0
        for user in users:
            user.auth_version += 1
            user.recovery_generation += 1
            if user.totp_habilitado and user.totp_secret_encrypted:
                # No reutilizar un TOTP del pequeño intervalo alrededor del corte.
                user.totp_last_step = max(user.totp_last_step or -1, int(now.timestamp()) // 30 + 1)
            if user.debe_cambiar_password:
                initial += 1
                db.add(AccesoInicialRestaurado(restauracion_id=row.id, usuario_id=user.id, creado_at=now))
        sessions = await db.execute(update(SesionAutenticacion).where(SesionAutenticacion.revoked_at.is_(None))
                                    .values(revoked_at=now))
        challenges = await db.execute(update(DesafioAutenticacion).values(revocado_at=now, secreto_pendiente_cifrado=None))
        codes = await db.execute(update(CodigoRecuperacion).where(CodigoRecuperacion.invalidado_at.is_(None))
                                 .values(invalidado_at=now))
        notifications = await db.execute(update(Notificacion).where(Notificacion.canal == 'email',
            Notificacion.estado.in_(['pendiente', 'fallida', 'enviando'])).values(estado='cancelada',
                secreto_temporal_encrypted=None, secreto_expira_at=None, ultimo_error='corte_restaurado',
                lease_owner=None, lease_hasta=None, generation=Notificacion.generation + 1))
        await db.execute(update(Notificacion).where(Notificacion.secreto_temporal_encrypted.is_not(None))
                         .values(secreto_temporal_encrypted=None, secreto_expira_at=None))
        operations = list((await db.scalars(select(OperacionInfraestructura).where(
            OperacionInfraestructura.estado.in_(OPEN)).with_for_update())).all())
        for operation in operations:
            operation.contexto_seguro = {**operation.contexto_seguro,
                'corte_restaurado': {'restauracion_id': str(row.id), 'fase_anterior': operation.fase}}
            operation.estado, operation.fase = 'incierta', 'restauracion_pendiente'
            operation.lease_owner = operation.lease_until = None
            operation.lease_generation += 1
            operation.error_codigo = 'corte_restaurado'
            operation.error_detalle_seguro = 'Reconciliar historia de tareas e inventario antes de reanudar; no repetir envíos'
            operation.updated_at = now
            if operation.identidad_infraestructura_id:
                await db.execute(update(CompromisoCapacidad).where(
                    CompromisoCapacidad.identidad_infraestructura_id == operation.identidad_infraestructura_id,
                    CompromisoCapacidad.liberado_at.is_(None)).values(estado='incierto', revision=CompromisoCapacidad.revision + 1))
        row.resumen = {'usuarios': len(users), 'sesiones_revocadas': sessions.rowcount,
            'desafios_revocados': challenges.rowcount, 'codigos_invalidados': codes.rowcount,
            'correos_cancelados': notifications.rowcount, 'accesos_iniciales_pendientes': initial,
            'operaciones_inciertas': len(operations)}
        await db.flush()
        return _presentar(row)


def _sha(value):
    from fastapi.encoders import jsonable_encoder
    return hashlib.sha256(json.dumps(jsonable_encoder(value), ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


async def evaluar_habilitacion(db, referencia, *, pve=None):
    """Sólo lecturas. La prueba humana de aplicaciones es adicional al sondeo."""
    from app.database import Base
    from app.models.identidad_infraestructura import IdentidadInfraestructura
    from app.models.servicio import Servicio, EstadoServicio
    from app.services import preflight_service, inventario_service, identidad_infra_service, infraestructura_io
    from app.services.vigencia_service import periodos_vigentes
    from app.services.orquestacion_service import _matches
    row = await db.scalar(select(Restauracion).where(Restauracion.referencia == referencia))
    if row is None or row.estado != 'pendiente':
        raise error(409, 'restauracion_no_pendiente', 'Preparar una copia con referencia nueva antes de habilitar')
    checks = {'configuracion': preflight_service.validar_configuracion(get_settings())}
    for name, check in [('datos', preflight_service.inspeccionar_datos),
                        ('claves', preflight_service.inspeccionar_claves),
                        ('ofertas', preflight_service.inspeccionar_ofertas)]:
        checks[name] = await check(db)
    issues = []
    if await db.scalar(select(OperacionInfraestructura.id).where(OperacionInfraestructura.estado.in_(OPEN)).limit(1)):
        issues.append('operaciones_abiertas_del_corte')
    if await db.scalar(select(CompromisoCapacidad.id).where(CompromisoCapacidad.estado == 'incierto').limit(1)):
        issues.append('capacidad_incierta_del_corte')
    identities = list((await db.scalars(select(IdentidadInfraestructura))).all())
    live = {str(i.resource_uuid): i for i in identities if i.ausencia_confirmada_at is None}
    stable_inventory = None
    try:
        if not checks['configuracion']['apto']: raise ValueError()
        inventory = await infraestructura_io.con_cliente(inventario_service.observar, pve=pve, timeout=30)
        # No autorizar una copia anterior a un alta/eliminación externa posterior.
        for resource in inventory['recursos'].values():
            mark = resource.get('marca')
            if mark and mark.get('resource_uuid') not in live:
                issues.append('recurso_nap_fuera_del_corte')
        for identity in live.values():
            observation = await identidad_infra_service.observar(identity, pve=pve)
            resource = inventory['recursos'].get(identity.vmid)
            ledger = await db.scalar(select(CompromisoCapacidad).where(
                CompromisoCapacidad.identidad_infraestructura_id == identity.id, CompromisoCapacidad.liberado_at.is_(None)))
            service = await db.get(Servicio, identity.servicio_id) if identity.servicio_id else None
            if (identity.estado != 'materializada' or observation.estado != 'propia' or resource is None
                    or resource.get('marca') != identidad_infra_service.marca(identity)
                    or resource['nodo'] != identity.nodo or not ledger or ledger.estado != 'materializado'
                    or not service or service.deleted_at or service.identidad_infraestructura_id != identity.id
                    or ledger.servicio_id != service.id or ledger.pedido_id != service.pedido_id):
                issues.append('identidad_y_compromiso_no_reconciliados'); continue
            allocation = service.asignacion_snapshot or {}
            disk = sum(resource['volumenes'].values())
            expected_status = 'running' if service.estado == EstadoServicio.RUNNING else (
                'stopped' if service.estado in {EstadoServicio.PAUSED, EstadoServicio.STOPPED} else None)
            if (not _matches(observation.config, allocation, {'storage': ledger.storage_id})
                    or observation.status != resource['estado'] or observation.status != expected_status
                    or allocation.get('vcpus') != resource['configurado_vcpus']
                    or allocation.get('ram_mb') != resource['configurado_ram_mb']
                    or allocation.get('disk_gb', 0) * 1024**3 != disk
                    or ledger.nodo != identity.nodo
                    or any(scope != ledger.storage_scope for scope, _ in resource['volumenes'])
                    or ledger.vcpus_retenidos < resource['vcpus']
                    or ledger.ram_mb_retenida < resource['ram_mb'] or ledger.disk_bytes_retenidos < disk):
                issues.append('asignacion_y_ledger_no_reconciliados')
            if observation.status == 'running':
                periods = await periodos_vigentes(db, service.id)
                from app.utils.clock import db_utc
                if not any(db_utc(p.inicio_at) <= clock.now() < db_utc(p.fin_exclusivo_at) for p in periods):
                    issues.append('recurso_encendido_sin_vigencia_actual')
        stable_inventory = {'cluster_id': inventory['cluster_id'], 'perfil': inventory['perfil'],
            'recursos': inventory['recursos'], 'destinos': inventory['destinos'], 'volumenes': inventory['volumenes']}
        stable_inventory = inventario_service.canonical_snapshot(stable_inventory)
    except Exception:
        issues.append('inventario_o_propiedad_no_verificables')
    # Digest privado: material sensible nunca sale del proceso. Omitir series de
    # métricas e historial voluminoso; cubrir decisiones, claves y control actuales.
    digest = {}
    for table in ['usuarios', 'catedras', 'pedidos', 'servicios', 'identidades_infraestructura',
                  'compromisos_capacidad', 'operaciones_infraestructura', 'vigencias_autorizadas',
                  'cambios_acceso_consola', 'accesos_iniciales_restaurados']:
        definition = Base.metadata.tables[table]
        values = (await db.execute(select(definition).order_by(*definition.primary_key.columns))).mappings().all()
        digest[table] = _sha([dict(value) for value in values])
    state = _sha({'tablas': digest, 'inventario': stable_inventory,
                  'configuracion': _sha(get_settings().model_dump(mode='json'))})
    return {'restauracion_id': str(row.id), 'referencia': row.referencia, 'estado_sha256': state,
            'apto': not issues and all(c['apto'] for c in checks.values()),
            'pendientes': sorted(set(issues)), 'comprobaciones': checks}


async def habilitar_restauracion(db, *, operador, prueba, pve=None):
    from app.schemas.restauracion import PruebaRestauracion
    operador = referencia_valida(operador)
    proof = PruebaRestauracion.model_validate(prueba)
    if get_settings().app_env == 'production' and proof.entorno != 'real':
        raise error(409, 'ensayo_simulado_no_operativo', 'Producción requiere evidencia de restauración real')
    async with bloqueo_capacidad(db):
        await _lock(db)
        row = await db.scalar(select(Restauracion).where(Restauracion.id == proof.restauracion_id).with_for_update())
        if not row or row.referencia != proof.referencia_corte or row.estado != 'pendiente':
            raise error(409, 'restauracion_no_pendiente', 'Revisar la referencia del corte pendiente')
        from app.utils.clock import db_utc
        if proof.inicio_at < db_utc(row.preparada_at):
            raise ValueError('La prueba separada debe ser posterior a la preparación de este corte')
        report = await evaluar_habilitacion(db, row.referencia, pve=pve)
        if not report['apto'] or report['estado_sha256'] != proof.estado_sha256:
            raise error(409, 'reconciliacion_restauracion_pendiente',
                        'Los datos o inventario requieren revisión y un nuevo informe antes de habilitar')
        row.estado, row.habilitada_at, row.habilitada_por = 'habilitada', clock.now(), operador
        row.prueba_referencia = proof.referencia_ensayo
        row.prueba_sha256 = _sha(proof.model_dump(mode='json'))
        row.estado_sha256 = report['estado_sha256']
        await db.flush()
        return _presentar(row)
