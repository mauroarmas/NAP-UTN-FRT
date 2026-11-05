"""Revisiones e inventario individual de consola; legacy queda desconocido."""
from alembic import op
import sqlalchemy as sa

revision = '009_01_consola'
down_revision = '009_01_base_cierre'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('usuarios', sa.Column('revision_admin', sa.Integer(), server_default='1', nullable=False))
    op.add_column('usuarios', sa.Column('identidad_consola', sa.String(200), nullable=True))
    op.add_column('usuarios', sa.Column('inventario_consola', sa.String(20), server_default='desconocido', nullable=False))
    op.add_column('usuarios', sa.Column('inventario_consola_ref', sa.String(200), nullable=True))
    op.add_column('usuarios', sa.Column('inventario_consola_actor', sa.String(200), nullable=True))
    op.add_column('usuarios', sa.Column('inventario_consola_historial', sa.JSON(), nullable=True))
    op.create_unique_constraint('uq_usuario_identidad_consola', 'usuarios', ['identidad_consola'])
    op.add_column('catedras', sa.Column('revision_admin', sa.Integer(), server_default='1', nullable=False))


def downgrade():
    raise RuntimeError('Restaurar copia verificada para rollback; no borrar inventario histórico')
