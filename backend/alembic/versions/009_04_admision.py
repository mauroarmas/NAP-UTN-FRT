"""Revisión de perfiles e identidad única en compromisos abiertos."""
from alembic import op
import sqlalchemy as sa

revision = '009_04_admision'
down_revision = '009_03_outbox'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('recurso_templates', sa.Column('revision', sa.Integer(), server_default='1', nullable=False))
    op.create_index('uq_compromiso_identidad_abierto', 'compromisos_capacidad', ['identidad_infraestructura_id'],
                    unique=True, postgresql_where=sa.text('liberado_at IS NULL'))


def downgrade():
    raise RuntimeError('Restaurar copia verificada; no eliminar revisiones ni exclusión de identidad')
