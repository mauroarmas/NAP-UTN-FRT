"""Contexto autorizado y límites de observación de operaciones durables."""
from alembic import op
import sqlalchemy as sa

revision = '009_05_operaciones'
down_revision = '009_04_admision'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('operaciones_infraestructura', sa.Column('contexto_seguro', sa.JSON(), nullable=False, server_default='{}'))
    op.add_column('operaciones_infraestructura', sa.Column('dispatch_started_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('operaciones_infraestructura', sa.Column('deadline_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    raise RuntimeError('Restaurar copia verificada: no borrar contexto de operaciones ni evidencia de dispatch')
