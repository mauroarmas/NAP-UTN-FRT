"""Pools deterministas: consulta sin efectos y preparación repetible del despliegue.

No concede ACL, adopta recursos ni modifica miembros de un pool existente.
"""
from sqlalchemy import select, or_, func

from app.models.catedra import Catedra
from app.models.pedido import Pedido
from app.models.servicio import Servicio
from app.models.identidad_infraestructura import IdentidadInfraestructura
from app.config import get_settings
from app.services.infraestructura_io import consultar, enviar, InfraNoVerificable
from app.services.inventario_service import marker
from app.utils.clock import clock
from app.utils.errors import error

PERMISOS = {'Pool.Allocate', 'VM.Allocate', 'VM.Audit', 'VM.PowerMgmt'}


def nombre_pool(catedra_id):
    if type(catedra_id) is not int or catedra_id <= 0:
        raise ValueError('Identificador de cátedra inválido')
    return f'catedra-{catedra_id}'


async def verificar(db, catedra_id, *, pve=None):
    category = await db.get(Catedra, catedra_id)
    if category is None:
        raise error(404, 'catedra_no_encontrada', 'Cátedra no encontrada')
    pool = nombre_pool(catedra_id)
    result = {'catedra_id': catedra_id, 'pool': pool, 'estado': 'requiere_atencion',
        'codigo': 'pool_no_verificable', 'mensaje': 'No se pudo comprobar la conexión o el acceso al pool. Volvé a consultar.',
        'verificado_at': clock.now().isoformat()}
    if not category.activa:
        return {**result, 'codigo': 'pool_catedra_inactiva', 'mensaje': 'La cátedra está inactiva. Revisá su estado antes de desplegar.'}
    try:
        permissions = await consultar('get_pool_permissions', pool, pve=pve)
        if permissions.estado != 'presente' or not isinstance(permissions.valor, dict):
            return result
        missing = sorted(p for p in PERMISOS if permissions.valor.get(p) not in (1, True))
        if missing:
            return {**result, 'codigo': 'pool_permisos_insuficientes',
                'mensaje': 'El portal no tiene los permisos necesarios para preparar y operar el pool. Revisá la cuenta de conexión a Proxmox.',
                'permisos_faltantes': missing}
        pools = await consultar('list_pools', pve=pve)
        if pools.estado != 'presente' or not isinstance(pools.valor, list) or any(not isinstance(p, dict) or not isinstance(p.get('poolid'), str) for p in pools.valor):
            return result
        if not any(p['poolid'] == pool for p in pools.valor):
            count = await db.scalar(select(func.count()).select_from(Servicio).where(
                Servicio.catedra_id == catedra_id, Servicio.deleted_at.is_(None)))
            if count:
                return {**result, 'codigo': 'pool_falta_con_servicios',
                    'mensaje': 'Hay servicios registrados, pero falta su pool. Revisá sus relaciones antes de continuar.'}
            return {**result, 'estado': 'sin_servicios', 'codigo': 'pool_pendiente',
                'mensaje': 'El pool se creará automáticamente al desplegar el primer servicio. No reserva recursos por sí mismo.'}
        observed = await consultar('get_pool', pool, pve=pve)
        if observed.estado != 'presente' or not isinstance(observed.valor, dict) or not isinstance(observed.valor.get('members'), list):
            return result
        identities = list((await db.scalars(select(IdentidadInfraestructura)
            .outerjoin(Pedido, Pedido.id == IdentidadInfraestructura.pedido_alta_id)
            .outerjoin(Servicio, Servicio.id == IdentidadInfraestructura.servicio_id)
            .where(or_(Pedido.catedra_id == catedra_id, Servicio.catedra_id == catedra_id),
                IdentidadInfraestructura.pool_catedra == pool,
                IdentidadInfraestructura.ausencia_confirmada_at.is_(None)))).all())
        expected = {(i.nodo, i.vmid): i for i in identities}
        from app.services.identidad_infra_service import marca
        for member in observed.valor['members']:
            if not isinstance(member, dict):
                return result
            if not isinstance(member.get('node'), str) or type(member.get('vmid')) is not int or member['vmid'] <= 0:
                return {**result, 'codigo': 'pool_miembros_sin_verificar',
                    'mensaje': 'El pool contiene recursos que requieren una revisión de administración antes de continuar.'}
            identity = expected.get((member.get('node'), member.get('vmid')))
            own = member.get('type') == 'lxc' and identity is not None and identity.cluster_id == get_settings().infrastructure_profile.get('cluster_id')
            if own:
                # El listado de miembros ya acredita pool/nodo/VMID. Leer sólo
                # su configuración evita repetir el inventario global por invitado.
                config = await consultar('get_lxc_config', identity.nodo, identity.vmid, pve=pve)
                own = config.estado == 'presente' and isinstance(config.valor, dict) and marker(config.valor) == marca(identity)
            if not own:
                return {**result, 'codigo': 'pool_miembros_sin_verificar',
                    'mensaje': 'El pool contiene recursos cuya relación con esta cátedra no está comprobada. No se moverán ni adoptarán automáticamente.'}
        return {**result, 'estado': 'preparada', 'codigo': 'pool_preparado',
            'mensaje': 'El pool existe y se comprobaron los permisos del portal y la pertenencia de sus recursos.'}
    except (InfraNoVerificable, ValueError):
        return result


async def asegurar(db, catedra_id, *, pve=None):
    result = await verificar(db, catedra_id, pve=pve)
    if result['codigo'] == 'pool_pendiente':
        try:
            await enviar('create_pool', result['pool'], pve=pve)
        except InfraNoVerificable:
            # Otro despliegue pudo crearlo, o el POST terminar después de vencer
            # la espera. Siempre releer; nunca inventar otro nombre ni borrar.
            pass
        result = await verificar(db, catedra_id, pve=pve)
        if result['codigo'] == 'pool_pendiente':
            result = {**result, 'codigo': 'pool_creacion_no_confirmada',
                'mensaje': 'No se confirmó la creación del pool. Se volverá a comprobar antes de crear el contenedor.'}
    if result['estado'] != 'preparada':
        raise error(409, result['codigo'], result['mensaje'])
    return result
