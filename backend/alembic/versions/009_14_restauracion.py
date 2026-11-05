"""Bloqueo de la copia restaurada; no modifica cuentas durante la migración."""
from alembic import op
import sqlalchemy as sa

revision = '009_14_restauracion'
down_revision = '009_13_cierre_constraints'
branch_labels = None
depends_on = None


def upgrade():
    # Un alta adquiere servicio_id al materializarse. Corregir también copias
    # que ya hayan aplicado la primera definición de la revisión 009_13.
    op.drop_constraint('ck_pedido_tipo_servicio', 'pedidos', type_='check')
    op.create_check_constraint('ck_pedido_tipo_servicio', 'pedidos',
                               "tipo = 'ALTA' OR (tipo = 'RENOVACION' AND servicio_id IS NOT NULL)")
    op.create_table('restauraciones',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('referencia', sa.String(200), nullable=False, unique=True),
        sa.Column('operador', sa.String(200), nullable=False),
        sa.Column('estado', sa.String(20), nullable=False),
        sa.Column('preparada_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('resumen', sa.JSON(), nullable=False),
        sa.Column('habilitada_at', sa.DateTime(timezone=True)),
        sa.Column('habilitada_por', sa.String(200)),
        sa.Column('prueba_referencia', sa.String(200)),
        sa.Column('prueba_sha256', sa.String(64)),
        sa.Column('estado_sha256', sa.String(64)),
        sa.CheckConstraint("estado IN ('pendiente','habilitada')", name='ck_restauracion_estado'),
        sa.CheckConstraint("estado != 'habilitada' OR (habilitada_at IS NOT NULL AND habilitada_por IS NOT NULL "
                           "AND prueba_referencia IS NOT NULL AND prueba_sha256 IS NOT NULL AND estado_sha256 IS NOT NULL)",
                           name='ck_restauracion_habilitada'))
    op.create_index('uq_restauracion_pendiente', 'restauraciones', ['estado'], unique=True,
                    postgresql_where=sa.text("estado = 'pendiente'"))
    op.create_table('accesos_iniciales_restaurados',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('restauracion_id', sa.Uuid(), sa.ForeignKey('restauraciones.id'), nullable=False),
        sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=False),
        sa.Column('creado_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('reemitido_at', sa.DateTime(timezone=True)),
        sa.Column('reemitido_por', sa.String(200)),
        sa.Column('referencia', sa.String(200)),
        sa.UniqueConstraint('restauracion_id', 'usuario_id', name='uq_acceso_restaurado_usuario'),
        sa.CheckConstraint('reemitido_at IS NULL OR (reemitido_por IS NOT NULL AND referencia IS NOT NULL)',
                           name='ck_acceso_restaurado_reemision'))
    op.create_index('ix_accesos_iniciales_restaurados_usuario_id', 'accesos_iniciales_restaurados', ['usuario_id'])


def downgrade():
    raise RuntimeError('No retirar la historia ni el bloqueo de restauración; recuperar una copia comprobada')
