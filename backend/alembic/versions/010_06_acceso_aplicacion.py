"""Códigos de apertura de aplicaciones con la sesión vigente de NAP."""
from alembic import op
import sqlalchemy as sa

revision = '010_06_acceso_aplicacion'
down_revision = '010_05_alta_materializada'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('accesos_aplicacion',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('codigo_sha256', sa.String(64), nullable=False, unique=True),
        sa.Column('sesion_id', sa.Uuid(), sa.ForeignKey('sesiones_autenticacion.id'), nullable=False),
        sa.Column('servicio_id', sa.Integer(), sa.ForeignKey('servicios.id'), nullable=False),
        sa.Column('creado_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expira_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('consumido_at', sa.DateTime(timezone=True)))
    op.create_index('ix_acceso_aplicacion_expira', 'accesos_aplicacion', ['expira_at'])
    op.create_index('ix_accesos_aplicacion_sesion_id', 'accesos_aplicacion', ['sesion_id'])
    op.create_index('ix_accesos_aplicacion_servicio_id', 'accesos_aplicacion', ['servicio_id'])


def downgrade():
    op.drop_table('accesos_aplicacion')
