"""Retirar secretos/counters antiguos sin borrar cantidades ni resolver legado.

Ejecutar en copia verificada, sin API/worker. La cuarentena cifrada es trabajo
del backfill revisado: esta revisión se niega a descartar un secreto pendiente.
No modifica fechas, identidades, operaciones, pertenencias ni recursos reales.
"""
from datetime import datetime,timezone
import hashlib
import json
from uuid import uuid4

from alembic import op
import sqlalchemy as sa

revision='009_13_cierre_constraints'
down_revision='009_12_bitacora_cierre'
branch_labels=None
depends_on=None

CHECKS={
    'recurso_templates':{
        'ck_template_recursos_positivos':'default_vcpus > 0 AND default_ram_mb > 0 AND default_disk_gb > 0',
    },
    'servicios':{
        'ck_servicio_recursos_positivos':'vcpus_asignados > 0 AND ram_asignada_mb > 0 AND disk_asignado_gb > 0',
        'ck_servicio_modelo':"modelo_servicio IS NULL OR modelo_servicio IN ('iaas','paas','saas')",
        'ck_servicio_disponibilidad':"disponibilidad_aplicacion IN ('no_verificada','preparando','utilizable','degradada','error')",
    },
    'pedidos':{
        'ck_pedido_revisiones':'revision >= 1 AND revision_decision >= 0',
        'ck_pedido_tipo_servicio':"tipo = 'ALTA' OR (tipo = 'RENOVACION' AND servicio_id IS NOT NULL)",
    },
}


def _canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)


def _hash(value):
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def upgrade():
    connection=op.get_bind()
    connection.execute(sa.text("SET LOCAL lock_timeout = '5s'"))
    connection.execute(sa.text('LOCK TABLE usuarios,servicios,pedidos,recurso_templates IN ACCESS EXCLUSIVE MODE'))
    if connection.scalar(sa.text('SELECT EXISTS(SELECT 1 FROM usuarios WHERE totp_secret IS NOT NULL)')):
        raise RuntimeError('Completar y verificar el backfill cifrado antes de retirar el factor legado')
    if connection.scalar(sa.text("SELECT EXISTS(SELECT 1 FROM servicios WHERE credenciales_acceso IS NOT NULL AND CAST(credenciales_acceso AS TEXT) <> 'null')")):
        raise RuntimeError('Completar y verificar la cuarentena cifrada antes de retirar credenciales antiguas')
    for name,checks in CHECKS.items():
        for key,condition in checks.items():
            if connection.scalar(sa.text(f'SELECT EXISTS(SELECT 1 FROM {name} WHERE NOT ({condition}))')):
                raise RuntimeError(f'Preflight requiere regularizar {key}; no se borraron filas')
    # Preservar los valores históricos como información, no como capacidad
    # reservada. Un ledger/identidad/período no se deduce de estos números.
    requests=sa.table('pedidos',sa.column('id',sa.Integer()),sa.column('template_id',sa.Integer()),
        sa.column('modelo_servicio',sa.String()),sa.column('asignacion_snapshot',sa.JSON()),
        *[sa.column(k,sa.Integer()) for k in ['reserva_vcpus','reserva_ram_mb','reserva_disk_gb']],
        sa.column('reserva_expira_at',sa.DateTime()))
    journal=sa.table('bitacora_cierre',sa.column('id',sa.Uuid()),
        *[sa.column(k,sa.String()) for k in ['entidad_tipo','entidad_id','fuente_sha256','resultado_sha256','accion','actor_institucional','referencia']],
        *[sa.column(k,sa.JSON()) for k in ['antes_seguro','despues_seguro','pendientes']],sa.column('creado_at',sa.DateTime(timezone=True)))
    for row in connection.execute(sa.select(requests)).mappings():
        values=[row[k] for k in ['reserva_vcpus','reserva_ram_mb','reserva_disk_gb']]
        if not any(values) and row['reserva_expira_at'] is None: continue
        before={'cantidades_autorizadas_legacy':dict(zip(['vcpus','ram_mb','disk_gb'],values)),
            'expiracion_legacy_utc':row['reserva_expira_at'].replace(tzinfo=timezone.utc).isoformat() if row['reserva_expira_at'] else None,
            'asignacion_snapshot':row['asignacion_snapshot']}
        snapshot=row['asignacion_snapshot']
        if snapshot is None and all(type(v) is int and v>0 for v in values):
            snapshot={'origen':'legado_cantidades_autorizadas','template_id':row['template_id'],
                'nombre':f"Asignación histórica del pedido #{row['id']}",'modelo_servicio':row['modelo_servicio'],
                **dict(zip(['vcpus','ram_mb','disk_gb'],values))}
            connection.execute(sa.update(requests).where(requests.c.id==row['id']).values(asignacion_snapshot=snapshot))
        after={'asignacion_snapshot':snapshot,'autoridad_capacidad':'compromisos_capacidad',
            'nueva_autorizacion':False,'fechas_y_propiedad_inferidas':False}
        connection.execute(sa.insert(journal).values(id=uuid4(),entidad_tipo='pedido',entidad_id=str(row['id']),
            fuente_sha256=_hash(before),resultado_sha256=_hash(after),accion='retirar_campos_reserva',
            antes_seguro=before,despues_seguro=after,pendientes=['revisar_legado_no_es_nueva_autorizacion'],
            actor_institucional='migracion_009_13',referencia='009_13_cierre_constraints',creado_at=datetime.now(timezone.utc)))
    for name,checks in CHECKS.items():
        for key,condition in checks.items(): op.create_check_constraint(key,name,condition)
    # Los FK y únicos de las autoridades ya existen en revisiones aditivas:
    # identidad por clúster/VMID retenido, ledger/operación abierta, versión,
    # decisión idempotente, vigencia e historia. No imponer unicidad por VMID
    # a registros históricos sin identidad: conservar el conflicto para revisión.
    op.drop_column('usuarios','totp_secret')
    op.drop_column('servicios','credenciales_acceso')
    for field in ['reserva_vcpus','reserva_ram_mb','reserva_disk_gb','reserva_expira_at']:
        op.drop_column('pedidos',field)


def downgrade():
    raise RuntimeError('Restaurar copia verificada y versión compatible; no recrear secretos ni contadores en paralelo')
