"""Historial inmutable de correcciones de calendario, sin alterar snapshots."""
from alembic import op
import sqlalchemy as sa

revision = '009_07_calendario'
down_revision = '009_06_worker_jobs'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('calendarios_historial',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('calendario_id', sa.Integer(), sa.ForeignKey('calendarios_lectivos.id'), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('actor_usuario_id', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=False),
        sa.Column('anterior', sa.JSON(), nullable=True),
        sa.Column('nuevo', sa.JSON(), nullable=False),
        sa.Column('creado_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('calendario_id', 'revision', name='uq_calendario_historial_revision'))


def downgrade():
    raise RuntimeError('Conservar historial y restaurar una copia verificada')
