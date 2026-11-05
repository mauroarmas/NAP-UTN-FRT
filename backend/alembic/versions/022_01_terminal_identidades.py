"""Identidades de consola gestionadas y sesiones de terminal (feature 022); aditiva.

DDL congelado: no importa modelos runtime. Downgrade sólo si las tablas están vacías.
"""
from alembic import op
import sqlalchemy as sa

revision = '022_01_terminal_identidades'
down_revision = '017_01_clave_acceso_servicio'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('identidades_consola',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=False, unique=True),
        sa.Column('identidad', sa.String(100), nullable=False, unique=True),
        sa.Column('password_cifrada', sa.Text(), nullable=False),
        sa.Column('estado', sa.String(20), nullable=False, server_default='en_preparacion'),
        sa.Column('pools_aplicados', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('revision', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('ultimo_error_seguro', sa.String(200)),
        sa.Column('reconciliada_at', sa.DateTime(timezone=True)),
        sa.Column('creada_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('actualizada_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("estado IN ('en_preparacion','lista','con_error','retirada')", name='ck_identidad_consola_estado'),
        sa.CheckConstraint("identidad ~ '^nap-u[0-9]+@pve$'", name='ck_identidad_consola_nombre'),
        sa.CheckConstraint('revision >= 1', name='ck_identidad_consola_revision'))
    op.create_table('sesiones_terminal',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=False),
        sa.Column('servicio_id', sa.Integer(), sa.ForeignKey('servicios.id'), nullable=False),
        sa.Column('nodo', sa.String(64), nullable=False),
        sa.Column('abierta_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ultimo_latido_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ultima_entrada_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('cierre_solicitado_at', sa.DateTime(timezone=True)),
        sa.Column('motivo_solicitud', sa.String(32)),
        sa.Column('cerrada_at', sa.DateTime(timezone=True)),
        sa.Column('motivo_cierre', sa.String(32)),
        sa.Column('duracion_s', sa.Integer()),
        sa.CheckConstraint("motivo_cierre IS NULL OR motivo_cierre IN ('inactividad','persona','retiro','baja','detencion',"
                           "'cuenta','administracion','reinicio_portal','error','limite')", name='ck_sesion_terminal_motivo'))
    op.create_index('ix_sesiones_terminal_usuario', 'sesiones_terminal', ['usuario_id', 'cerrada_at'])
    op.create_index('ix_sesiones_terminal_servicio', 'sesiones_terminal', ['servicio_id', 'cerrada_at'])


def downgrade():
    bind = op.get_bind()
    for tabla in ('sesiones_terminal', 'identidades_consola'):
        if bind.execute(sa.text(f'SELECT 1 FROM {tabla} LIMIT 1')).first():
            raise RuntimeError(f'La tabla {tabla} tiene datos; no se puede revertir sin perderlos')
    op.drop_index('ix_sesiones_terminal_servicio', table_name='sesiones_terminal')
    op.drop_index('ix_sesiones_terminal_usuario', table_name='sesiones_terminal')
    op.drop_table('sesiones_terminal')
    op.drop_table('identidades_consola')
