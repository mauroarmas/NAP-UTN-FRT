"""Observación por minuto, contadores exactos y consumo histórico conservado."""
from alembic import op
import sqlalchemy as sa

revision = '009_11_observacion'
down_revision = '009_10_identidad_preparacion'
branch_labels = None
depends_on = None


def upgrade():
    for direction in ['in', 'out']:
        op.alter_column('metricas_snapshots', f'net_{direction}_bytes', new_column_name=f'net_{direction}_legacy',
            existing_type=sa.Float(), nullable=True)
        op.add_column('metricas_snapshots', sa.Column(f'net_{direction}_bytes', sa.BigInteger()))
        op.execute(sa.text(f'''UPDATE metricas_snapshots SET net_{direction}_bytes =
            CASE WHEN net_{direction}_legacy >= 0 AND net_{direction}_legacy <= 9007199254740991
                AND net_{direction}_legacy = trunc(net_{direction}_legacy::numeric)
            THEN net_{direction}_legacy::bigint ELSE NULL END'''))
    for name in ['cpu_usage_percent', 'ram_usage_mb', 'disk_usage_gb']:
        op.alter_column('metricas_snapshots', name, existing_type=sa.Float(), nullable=True)
    op.alter_column('metricas_snapshots', 'timestamp', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True),
        postgresql_using="timestamp AT TIME ZONE 'UTC'")
    for column in [
        sa.Column('intervalo_at', sa.DateTime(timezone=True)),
        sa.Column('calidad', sa.String(20), nullable=False, server_default='no_confirmada'),
        sa.Column('estado_observado', sa.String(20)), sa.Column('aplicacion_saludable', sa.Boolean()),
        sa.Column('uptime_s', sa.BigInteger()), sa.Column('epoca_contador', sa.String(64)),
        sa.Column('ram_max_mb', sa.Float()), sa.Column('disk_max_bytes', sa.BigInteger()),
        sa.Column('vcpus_observadas', sa.Integer()), sa.Column('net_in_delta', sa.BigInteger()),
        sa.Column('net_out_delta', sa.BigInteger()),
        sa.Column('duracion_observada_s', sa.Integer(), nullable=False, server_default='0'),
    ]:
        op.add_column('metricas_snapshots', column)
    # Los duplicados históricos permanecen con intervalo NULL y sin cobertura.
    op.create_unique_constraint('uq_metrica_servicio_minuto', 'metricas_snapshots', ['servicio_id', 'intervalo_at'])
    op.create_index('ix_metrica_servicio_fecha', 'metricas_snapshots', ['servicio_id', 'timestamp'])
    op.create_check_constraint('ck_metrica_calidad', 'metricas_snapshots', "calidad IN ('confirmada','no_confirmada')")
    for name, field in [('net_in','net_in_bytes'), ('net_out','net_out_bytes'), ('delta_in','net_in_delta'), ('delta_out','net_out_delta')]:
        op.create_check_constraint('ck_metrica_' + name, 'metricas_snapshots', f'{field} IS NULL OR {field} >= 0')
    op.create_check_constraint('ck_metrica_duracion', 'metricas_snapshots', 'duracion_observada_s >= 0 AND duracion_observada_s <= 120')

    op.create_table('incidentes',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('servicio_id', sa.Integer(), sa.ForeignKey('servicios.id'), nullable=False),
        sa.Column('tipo', sa.String(32), nullable=False),
        sa.Column('estado', sa.String(10), nullable=False, server_default='abierto'),
        sa.Column('abierto_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ultima_observacion_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('resuelto_at', sa.DateTime(timezone=True)),
        sa.Column('regla_version', sa.String(40), nullable=False), sa.Column('evidencia', sa.JSON(), nullable=False),
        sa.CheckConstraint("estado IN ('abierto','resuelto')", name='ck_incidente_estado'),
        sa.CheckConstraint("tipo IN ('caida','cpu_sostenida','ram_sostenida','vencimiento_no_aplicado','operacion_incierta')", name='ck_incidente_tipo'))
    op.create_index('uq_incidente_abierto', 'incidentes', ['servicio_id','tipo'], unique=True,
        postgresql_where=sa.text("estado = 'abierto'"))
    op.create_index('ix_incidente_servicio_fecha', 'incidentes', ['servicio_id','abierto_at'])

    op.create_table('metricas_resumen_diario',
        sa.Column('servicio_id', sa.Integer(), sa.ForeignKey('servicios.id'), primary_key=True),
        sa.Column('fecha_local', sa.Date(), primary_key=True), sa.Column('zona_horaria', sa.String(64), primary_key=True),
        sa.Column('catedra_id', sa.Integer(), sa.ForeignKey('catedras.id'), nullable=False),
        *[sa.Column(name, sa.Integer(), nullable=False) for name in ['intervalos_esperados','intervalos_validos','segundos_observados','segundos_running']],
        sa.Column('cpu_integral', sa.Float(), nullable=False), sa.Column('cpu_max', sa.Float()),
        sa.Column('ram_integral_mb_s', sa.Float(), nullable=False), sa.Column('ram_max_mb', sa.Float()),
        sa.Column('disk_max_bytes', sa.BigInteger()),
        sa.Column('trafico_in_bytes', sa.Numeric(30,0), nullable=False), sa.Column('trafico_out_bytes', sa.Numeric(30,0), nullable=False),
        sa.Column('vcpu_segundos', sa.BigInteger()), sa.Column('ram_asignada_mb_segundos', sa.BigInteger()),
        sa.Column('disk_asignado_byte_segundos', sa.Numeric(30,0)),
        sa.Column('periodo_cerrado', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('agregado_at', sa.DateTime(timezone=True), nullable=False), sa.Column('detalle_purgado_at', sa.DateTime(timezone=True)),
        sa.CheckConstraint('intervalos_validos >= 0 AND intervalos_validos <= intervalos_esperados', name='ck_resumen_cobertura'),
        sa.CheckConstraint('segundos_observados >= 0 AND segundos_running >= 0', name='ck_resumen_segundos'))
    op.create_index('ix_resumen_catedra_fecha', 'metricas_resumen_diario', ['catedra_id','fecha_local'])


def downgrade():
    raise RuntimeError('No descartar contadores ni consumo histórico; restaurar una copia verificada')
